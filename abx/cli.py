"""CLI for ABX extraction."""

import os
import sys
import tempfile
import uuid
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import click
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

from abx.cleaner import clean_html
from abx.db import SCHEMA_VERSION, init_db
from abx.epub_parser import parse_epub
from abx.llm import (
    compute_prompt_hash,
    download_batch_results,
    extract_stories_sync,
    parse_batch_results,
    poll_batch,
    prepare_batch_input,
    resolve_model,
    submit_batch,
)
from abx.persistence import (
    check_idempotency,
    store_book,
    store_chapter,
    store_chapter_llm_result,
    store_llm_run,
    store_stories,
)

console = Console()


@click.group()
def cli():
    """ABX - Apple Books EPUB extraction with LLM-powered story analysis."""
    pass


@cli.command()
@click.option("--epub", required=True, type=click.Path(exists=True, path_type=Path), help="Path to EPUB file")
@click.option("--db", required=True, type=click.Path(path_type=Path), help="Path to SQLite database")
@click.option("--schema", required=True, type=click.Path(exists=True, path_type=Path), help="Path to story JSON schema")
@click.option("--model", default="auto", help="Model name (auto = best available)")
@click.option("--batch/--no-batch", default=True, help="Use batch mode (default: on)")
@click.option("--sync", is_flag=True, help="Force synchronous mode")
@click.option("--parallel", default=4, help="Parallel workers for local processing")
@click.option("--clean-html", "clean_html_mode", type=click.Choice(["loose", "strict"]), default="loose", help="HTML cleaning mode")
@click.option("--skip-boilerplate/--no-skip-boilerplate", default=True, help="Skip boilerplate chapters (copyright, contents, etc.)")
@click.option("--chapter-limit", default=999, help="Max chapters to process")
@click.option("--retry", default=3, help="LLM retry attempts")
@click.option("--max-input-tokens", default=0, help="Max input tokens (0 = no limit)")
@click.option("--fail-on-warnings", is_flag=True, help="Treat warnings as fatal")
@click.option("--verbose", is_flag=True, help="Verbose output")
def extract(
    epub: Path,
    db: Path,
    schema: Path,
    model: str,
    batch: bool,
    sync: bool,
    parallel: int,
    clean_html_mode: str,
    skip_boilerplate: bool,
    chapter_limit: int,
    retry: int,
    max_input_tokens: int,
    fail_on_warnings: bool,
    verbose: bool,
):
    """Extract stories from an EPUB file."""
    # Resolve sync mode
    if sync:
        batch = False

    # Check for API key
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        console.print("[red]Error: OPENAI_API_KEY environment variable not set[/red]")
        sys.exit(2)

    # Initialize database
    console.print(f"[cyan]Initializing database: {db}[/cyan]")
    conn = init_db(db)

    # Parse EPUB
    console.print(f"[cyan]Parsing EPUB: {epub.name}[/cyan]")
    metadata, chapters = parse_epub(epub, chapter_limit, skip_boilerplate)

    console.print(f"[green]Found {len(chapters)} chapters[/green]")
    if verbose:
        console.print(f"[dim]Title: {metadata.title}[/dim]")
        console.print(f"[dim]Authors: {', '.join(metadata.authors)}[/dim]")
        console.print(f"[dim]SHA256: {metadata.sha256}[/dim]")

    # Generate book_id
    book_id = f"book_{metadata.sha256[:16]}"

    # Store book metadata
    store_book(
        conn,
        book_id,
        {
            "sha256": metadata.sha256,
            "title": metadata.title,
            "authors": metadata.authors,
            "publisher": metadata.publisher,
            "published_date": metadata.published_date,
            "language": metadata.language,
            "source_path": metadata.source_path,
        },
    )

    # Clean chapters in parallel
    console.print(f"[cyan]Cleaning HTML ({clean_html_mode} mode)...[/cyan]")

    cleaned_chapters = []
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Cleaning chapters...", total=len(chapters))

        with ProcessPoolExecutor(max_workers=parallel) as executor:
            futures = {executor.submit(clean_html, ch.html_content, clean_html_mode): ch for ch in chapters}

            for future in as_completed(futures):
                ch = futures[future]
                clean_text = future.result()

                chapter_id = f"chapter_{book_id}_{ch.idx}"
                cleaned_chapters.append((chapter_id, ch, clean_text))

                # Store chapter
                store_chapter(
                    conn,
                    chapter_id,
                    book_id,
                    ch.idx,
                    ch.title,
                    ch.html_content,
                    clean_text,
                    ch.href,
                )

                progress.update(task, advance=1)

    console.print(f"[green]Cleaned {len(cleaned_chapters)} chapters[/green]")

    # Resolve model
    resolved_model = resolve_model(model)
    console.print(f"[cyan]Using model: {resolved_model}[/cyan]")

    # Compute prompt hash for idempotency
    book_context = f"Title: {metadata.title}, Authors: {', '.join(metadata.authors)}"
    with open(schema) as f:
        schema_json = f.read()

    sample_chapter_text = cleaned_chapters[0][2] if cleaned_chapters else ""
    prompt_hash = compute_prompt_hash(sample_chapter_text, book_context, schema_json)

    # Check idempotency
    existing_run_id = check_idempotency(conn, metadata.sha256, resolved_model, prompt_hash)
    if existing_run_id:
        console.print(f"[yellow]Found existing run: {existing_run_id}[/yellow]")
        console.print("[yellow]Skipping extraction (idempotent)[/yellow]")
        conn.close()
        sys.exit(0)

    # Generate run_id
    run_id = f"run_{uuid.uuid4().hex[:16]}"
    baml_version = "0.63.0"  # TODO: Get from package

    # LLM extraction
    warnings = []

    if batch:
        console.print("[cyan]Submitting batch job...[/cyan]")

        # Prepare batch input
        with tempfile.TemporaryDirectory() as tmpdir:
            batch_input_path = Path(tmpdir) / "batch_input.jsonl"
            batch_chapters = [(cid, text, book_context) for cid, _, text in cleaned_chapters]
            prepare_batch_input(batch_chapters, batch_input_path)

            # Submit batch
            batch_job_id = submit_batch(batch_input_path, api_key)
            console.print(f"[green]Batch job submitted: {batch_job_id}[/green]")

            # Store run
            store_llm_run(conn, run_id, book_id, resolved_model, prompt_hash, baml_version, batch_job_id)

            # Poll batch
            console.print("[cyan]Polling batch job (this may take a while)...[/cyan]")
            batch_result = poll_batch(batch_job_id, api_key)

            if batch_result["status"] != "completed":
                console.print(f"[red]Batch job failed: {batch_result['status']}[/red]")
                conn.close()
                sys.exit(2)

            # Download results
            results_path = Path(tmpdir) / "batch_results.jsonl"
            download_batch_results(batch_result["output_file_id"], api_key, results_path)

            # Parse results
            console.print("[cyan]Processing batch results...[/cyan]")
            results = parse_batch_results(results_path)

            # Store results
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                console=console,
            ) as progress:
                task = progress.add_task("Storing results...", total=len(results))

                for chapter_id, result in results.items():
                    # Store LLM result
                    store_chapter_llm_result(
                        conn,
                        chapter_id,
                        run_id,
                        result.status,
                        result.input_tokens,
                        result.output_tokens,
                        result.duration_ms,
                        result.error,
                    )

                    # Store stories
                    if result.stories:
                        store_stories(conn, chapter_id, result.stories)

                    if result.error:
                        warnings.append(f"{chapter_id}: {result.error}")

                    progress.update(task, advance=1)

    else:
        # Synchronous mode
        console.print("[cyan]Running synchronous extraction...[/cyan]")

        # Store run
        store_llm_run(conn, run_id, book_id, resolved_model, prompt_hash, baml_version)

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Extracting stories...", total=len(cleaned_chapters))

            for chapter_id, ch, clean_text in cleaned_chapters:
                result = extract_stories_sync(clean_text, book_context, resolved_model, max_input_tokens, retry)

                # Store LLM result
                store_chapter_llm_result(
                    conn,
                    chapter_id,
                    run_id,
                    result.status,
                    result.input_tokens,
                    result.output_tokens,
                    result.duration_ms,
                    result.error,
                )

                # Store stories
                if result.stories:
                    store_stories(conn, chapter_id, result.stories)

                if result.error:
                    warnings.append(f"{chapter_id}: {result.error}")

                progress.update(task, advance=1)

    # Summary
    cursor = conn.execute("SELECT COUNT(*) FROM stories")
    total_stories = cursor.fetchone()[0]

    cursor = conn.execute("SELECT SUM(input_tokens), SUM(output_tokens) FROM chapter_llm WHERE run_id = ?", (run_id,))
    total_input, total_output = cursor.fetchone()

    console.print("\n[bold green]Extraction complete![/bold green]")
    console.print(f"[green]Chapters: {len(cleaned_chapters)}[/green]")
    console.print(f"[green]Stories: {total_stories}[/green]")
    console.print(f"[green]Tokens: in={total_input:,} out={total_output:,}[/green]")
    console.print(f"[green]Model: {resolved_model}[/green]")
    console.print(f"[green]Prompt-hash: {prompt_hash[:16]}[/green]")
    console.print(f"[green]Schema: v{SCHEMA_VERSION}[/green]")
    console.print(f"[green]DB: {db}[/green]")

    if warnings:
        console.print(f"\n[yellow]Warnings: {len(warnings)}[/yellow]")
        if verbose:
            for warning in warnings[:10]:
                console.print(f"[dim]  {warning}[/dim]")

    conn.close()

    # Exit code
    if warnings and fail_on_warnings:
        sys.exit(1)
    elif warnings:
        sys.exit(1)
    else:
        sys.exit(0)


def main():
    """Entry point."""
    cli()


if __name__ == "__main__":
    main()
