"""CLI for ABXGeo precision geocoding."""

import sqlite3
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from abxgeo.db_migrate import migrate_db

console = Console()


@click.group()
def cli():
    """ABXGeo - Precision geocoding for ABX-extracted locations."""
    pass


@cli.command()
@click.option("--db", required=True, type=click.Path(exists=True, path_type=Path), help="Path to SQLite database")
@click.option("--email", required=True, help="Email for Nominatim geocoder compliance")
@click.option("--batch/--incremental", default=True, help="Batch (all unresolved) or incremental (low confidence)")
@click.option("--filter", "filter_clause", help="SQL WHERE clause for filtering locations")
@click.option("--book-id", help="Filter by book_id (shorthand)")
@click.option("--confidence-threshold", default=0.7, type=float, help="Re-resolve if confidence < threshold")
@click.option("--model", default="auto", help="Model name (auto = best available)")
@click.option("--dry-run", is_flag=True, help="Show proposed changes without writing")
@click.option("--verbose", is_flag=True, help="Verbose output")
def resolve(
    db: Path,
    email: str,
    batch: bool,
    filter_clause: str | None,
    book_id: str | None,
    confidence_threshold: float,
    model: str,
    dry_run: bool,
    verbose: bool,
):
    """
    Resolve vague locations to precise addresses and coordinates.

    Examples:
        # Resolve all unresolved locations
        abxgeo resolve --db library.sqlite --email you@example.com

        # Re-resolve low-confidence locations
        abxgeo resolve --db library.sqlite --email you@example.com --incremental

        # Resolve only locations from one book
        abxgeo resolve --db library.sqlite --email you@example.com --book-id book_abc123

        # Custom filter
        abxgeo resolve --db library.sqlite --email you@example.com --filter "place_type = 'factory'"

        # Dry run to preview changes
        abxgeo resolve --db library.sqlite --email you@example.com --dry-run
    """
    console.print("[bold cyan]ABXGeo - Precision Geocoding[/bold cyan]\n")

    # Ensure database is migrated
    migrate_db(db)

    # Connect to database
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row

    # Build WHERE clause
    where_parts = ["place_name IS NOT NULL"]

    if batch:
        # Batch mode: all unresolved
        where_parts.append("resolved_address IS NULL")
    else:
        # Incremental mode: low confidence or unresolved
        where_parts.append(
            f"(resolved_address IS NULL OR resolution_confidence IS NULL OR resolution_confidence < {confidence_threshold})"
        )

    if book_id:
        where_parts.append(f"story_id LIKE '{book_id}%'")

    if filter_clause:
        where_parts.append(f"({filter_clause})")

    where_sql = " AND ".join(where_parts)

    # Query locations to resolve
    query = f"""
        SELECT
            sl.story_id,
            sl.loc_idx,
            sl.place_name,
            sl.lat,
            sl.lon,
            sl.place_type,
            sl.geo_precision,
            sl.note,
            sl.resolved_address,
            sl.resolution_confidence,
            s.title as story_title,
            s.summary as story_summary,
            s.chapter_id
        FROM story_locations sl
        JOIN stories s ON sl.story_id = s.story_id
        WHERE {where_sql}
        ORDER BY sl.story_id, sl.loc_idx
    """

    if verbose:
        console.print(f"[dim]Query: {query}[/dim]\n")

    cursor = conn.execute(query)
    locations = cursor.fetchall()

    if not locations:
        console.print("[yellow]No locations found matching criteria[/yellow]")
        conn.close()
        sys.exit(0)

    console.print(f"[green]Found {len(locations)} locations to resolve[/green]\n")

    if dry_run:
        console.print("[yellow]DRY RUN MODE - No changes will be written[/yellow]\n")

    # Display locations to process
    if verbose or dry_run:
        table = Table(title="Locations to Resolve")
        table.add_column("Place Name", style="cyan")
        table.add_column("Type", style="dim")
        table.add_column("Note", style="dim", max_width=40)
        table.add_column("Current Status", style="yellow")

        for loc in locations[:10]:  # Show first 10
            status = f"Resolved ({loc['resolution_confidence']:.2f})" if loc["resolved_address"] else "Unresolved"
            table.add_row(
                loc["place_name"] or "N/A",
                loc["place_type"] or "N/A",
                (loc["note"] or "")[:40],
                status,
            )

        if len(locations) > 10:
            table.add_row("...", "...", "...", f"({len(locations) - 10} more)")

        console.print(table)
        console.print()

    if dry_run:
        console.print("[yellow]Dry run complete. Use without --dry-run to execute.[/yellow]")
        conn.close()
        sys.exit(0)

    # Import resolver
    from abxgeo.resolver import LocationResolver

    # Initialize resolver
    google_api_key = None  # TODO: Support Google API key from env/config
    resolver = LocationResolver(
        db_path=str(db),
        user_email=email,
        google_api_key=google_api_key,
        verbose=verbose,
    )

    # Process locations
    success_count = 0
    fail_count = 0

    with console.status("[bold green]Resolving locations...") as status:
        for i, loc in enumerate(locations, 1):
            status.update(f"[bold green]Resolving {i}/{len(locations)}: {loc['place_name']}")

            # Check if should skip
            if resolver.should_skip_resolution(
                story_id=loc["story_id"],
                loc_idx=loc["loc_idx"],
                resolved_address=loc["resolved_address"],
                resolution_confidence=loc["resolution_confidence"],
                incremental=not batch,
            ):
                continue

            # Resolve location
            try:
                resolution = resolver.resolve(
                    story_id=loc["story_id"],
                    loc_idx=loc["loc_idx"],
                    place_name=loc["place_name"],
                    place_type=loc["place_type"],
                    note=loc["note"],
                    lat=loc["lat"],
                    lon=loc["lon"],
                    geo_precision=loc["geo_precision"],
                    story_title=loc["story_title"],
                    story_summary=loc["story_summary"],
                )

                if resolution:
                    # Persist resolution
                    resolver.persist_resolution(resolution)
                    success_count += 1
                else:
                    fail_count += 1

            except Exception as e:
                console.print(f"[red]Failed to resolve {loc['place_name']}: {e}[/red]")
                fail_count += 1

    console.print(f"\n[green]✓ Successfully resolved {success_count} locations[/green]")
    if fail_count > 0:
        console.print(f"[yellow]⚠ Failed to resolve {fail_count} locations[/yellow]")

    conn.close()


@cli.command()
@click.option("--db", required=True, type=click.Path(exists=True, path_type=Path), help="Path to SQLite database")
def migrate(db: Path):
    """
    Migrate database schema to latest version.

    This command adds the new geocoding columns to story_locations
    and creates the geocode_cache table.
    """
    console.print("[bold cyan]Database Migration[/bold cyan]\n")
    migrate_db(db)


@cli.command()
@click.option("--db", required=True, type=click.Path(exists=True, path_type=Path), help="Path to SQLite database")
def stats(db: Path):
    """Show geocoding resolution statistics."""
    console.print("[bold cyan]Geocoding Statistics[/bold cyan]\n")

    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row

    # Total locations
    cursor = conn.execute("SELECT COUNT(*) FROM story_locations WHERE place_name IS NOT NULL")
    total = cursor.fetchone()[0]

    # Resolved locations
    cursor = conn.execute("SELECT COUNT(*) FROM story_locations WHERE resolved_address IS NOT NULL")
    resolved = cursor.fetchone()[0]

    # By precision
    cursor = conn.execute("""
        SELECT resolved_precision, COUNT(*) as count
        FROM story_locations
        WHERE resolved_address IS NOT NULL
        GROUP BY resolved_precision
        ORDER BY count DESC
    """)
    by_precision = cursor.fetchall()

    # Average confidence
    cursor = conn.execute("SELECT AVG(resolution_confidence) FROM story_locations WHERE resolved_address IS NOT NULL")
    avg_confidence = cursor.fetchone()[0] or 0.0

    # Display stats
    table = Table(title="Geocoding Resolution Statistics")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Total Locations", str(total))
    table.add_row("Resolved", str(resolved))
    table.add_row("Unresolved", str(total - resolved))
    table.add_row("Resolution Rate", f"{(resolved / total * 100):.1f}%" if total > 0 else "N/A")
    table.add_row("Avg Confidence", f"{avg_confidence:.3f}")

    console.print(table)
    console.print()

    if by_precision:
        prec_table = Table(title="By Precision Level")
        prec_table.add_column("Precision", style="cyan")
        prec_table.add_column("Count", style="green")

        for row in by_precision:
            prec_table.add_row(row["resolved_precision"] or "unknown", str(row["count"]))

        console.print(prec_table)

    conn.close()


@cli.command()
@click.option("--db", required=True, type=click.Path(exists=True, path_type=Path), help="Path to SQLite database")
@click.option("--older-than", default="7d", help="Clear cache entries older than (e.g., 7d, 30d)")
def clear_cache(db: Path, older_than: str):
    """Clear expired geocoding cache entries."""
    console.print(f"[cyan]Clearing cache entries older than {older_than}...[/cyan]")

    # Parse older_than (simple implementation)
    if older_than.endswith("d"):
        try:
            days = int(older_than[:-1])
        except ValueError:
            console.print("[red]Invalid --older-than format. Use format like '7d', '30d'[/red]")
            sys.exit(1)
    else:
        console.print("[red]Invalid --older-than format. Use format like '7d', '30d'[/red]")
        sys.exit(1)

    conn = sqlite3.connect(db)

    # Delete expired entries (using parameterized query for safety)
    cursor = conn.execute(
        "DELETE FROM geocode_cache WHERE datetime(fetched_at, '+' || ? || ' days') < datetime('now')", (days,)
    )
    deleted = cursor.rowcount

    conn.commit()
    conn.close()

    console.print(f"[green]Deleted {deleted} cache entries[/green]")


def main():
    """Entry point."""
    cli()


if __name__ == "__main__":
    main()
