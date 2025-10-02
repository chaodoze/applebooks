"""LLM integration with OpenAI Responses API via BAML."""

import asyncio
import hashlib
import json
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import tiktoken
from openai import OpenAI

# Add project root to path to find baml_client
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

try:
    from baml_client import b
except ImportError:
    # Fallback for testing without BAML
    b = None


@dataclass
class LLMResult:
    """Result from LLM extraction."""

    stories: list[dict[str, Any]]
    input_tokens: int
    output_tokens: int
    duration_ms: int
    status: str  # ok, error, chunked
    error: str | None = None


def compute_prompt_hash(chapter_text: str, book_context: str, schema_json: str) -> str:
    """Compute hash of prompt + schema for idempotency."""
    combined = f"{chapter_text}\n{book_context}\n{schema_json}"
    return hashlib.sha256(combined.encode()).hexdigest()


def estimate_tokens(text: str, model: str = "gpt-4o") -> int:
    """Estimate token count for text."""
    try:
        encoding = tiktoken.encoding_for_model(model)
    except KeyError:
        encoding = tiktoken.get_encoding("cl100k_base")
    return len(encoding.encode(text))


def resolve_model(model_arg: str) -> str:
    """Resolve model name from argument."""
    if model_arg == "auto":
        return "gpt-5"
    return model_arg


def extract_stories_sync(
    chapter_text: str,
    book_context: str,
    model: str,
    max_input_tokens: int = 0,
    retry: int = 3,
) -> LLMResult:
    """
    Extract stories from a chapter using BAML (synchronous mode).

    Args:
        chapter_text: Cleaned chapter text
        book_context: Book metadata context
        model: Model name
        max_input_tokens: Maximum input tokens (0 = no limit)
        retry: Number of retries on failure
    """
    start_time = time.time()

    # Safety check for token limits
    estimated_tokens = estimate_tokens(chapter_text + book_context, model)
    if max_input_tokens > 0 and estimated_tokens > max_input_tokens:
        return LLMResult(
            stories=[],
            input_tokens=estimated_tokens,
            output_tokens=0,
            duration_ms=0,
            status="error",
            error=f"Input exceeds max_input_tokens: {estimated_tokens} > {max_input_tokens}",
        )

    # Try extraction with retries
    last_error = None
    for attempt in range(retry):
        try:
            # Call BAML function (async)
            stories = asyncio.run(b.ExtractStories(chapter_text=chapter_text, book_context=book_context))

            duration_ms = int((time.time() - start_time) * 1000)

            # Process stories - generate UUIDs for auto_or_uuid
            processed_stories = []
            for story in stories:
                story_dict = story if isinstance(story, dict) else story.model_dump()
                if story_dict.get("story_id") == "auto_or_uuid":
                    story_dict["story_id"] = str(uuid.uuid4())
                processed_stories.append(story_dict)

            return LLMResult(
                stories=processed_stories,
                input_tokens=estimated_tokens,
                output_tokens=estimate_tokens(json.dumps(processed_stories)),
                duration_ms=duration_ms,
                status="ok",
            )
        except Exception as e:
            last_error = str(e)
            if attempt < retry - 1:
                time.sleep(2**attempt)  # Exponential backoff
            continue

    duration_ms = int((time.time() - start_time) * 1000)
    return LLMResult(
        stories=[],
        input_tokens=estimated_tokens,
        output_tokens=0,
        duration_ms=duration_ms,
        status="error",
        error=f"Failed after {retry} attempts: {last_error}",
    )


def prepare_batch_input(
    chapters: list[tuple[str, str, str]],  # (chapter_id, clean_text, book_context)
    output_path: Path,
) -> int:
    """
    Prepare batch input file for OpenAI Batch API.

    Args:
        chapters: List of (chapter_id, clean_text, book_context)
        output_path: Path to write JSONL batch input

    Returns:
        Number of requests prepared
    """
    with open(output_path, "w") as f:
        for chapter_id, clean_text, book_context in chapters:
            request = {
                "custom_id": chapter_id,
                "method": "POST",
                "url": "/v1/chat/completions",
                "body": {
                    "model": "gpt-5",
                    "reasoning_effort": "high",
                    "messages": [
                        {
                            "role": "system",
                            "content": "You are extracting structured stories from a chapter of a book about Apple Computer history.",
                        },
                        {
                            "role": "user",
                            "content": f"Book context: {book_context}\n\nChapter text:\n---\n{clean_text}\n---\n\nExtract 0 or more Story objects from this chapter. Return a JSON array.",
                        },
                    ],
                    "response_format": {
                        "type": "json_schema",
                        "json_schema": {
                            "name": "stories",
                            "strict": True,
                            "schema": load_story_schema(),
                        },
                    },
                },
            }
            f.write(json.dumps(request) + "\n")
    return len(chapters)


def load_story_schema() -> dict:
    """Load story JSON schema."""
    schema_path = Path(__file__).parent.parent / "schema" / "story.schema.json"
    with open(schema_path) as f:
        return json.load(f)


def submit_batch(input_file: Path, api_key: str) -> str:
    """Submit batch job to OpenAI."""
    client = OpenAI(api_key=api_key)

    with open(input_file, "rb") as f:
        batch_input_file = client.files.create(file=f, purpose="batch")

    batch = client.batches.create(
        input_file_id=batch_input_file.id,
        endpoint="/v1/chat/completions",
        completion_window="24h",
    )

    return batch.id


def poll_batch(batch_id: str, api_key: str, poll_interval: int = 60) -> dict:
    """
    Poll batch job until completion.

    Returns:
        Batch status dict with results
    """
    client = OpenAI(api_key=api_key)

    while True:
        batch = client.batches.retrieve(batch_id)

        if batch.status in ["completed", "failed", "expired", "cancelled"]:
            return {
                "status": batch.status,
                "output_file_id": batch.output_file_id if batch.status == "completed" else None,
                "error_file_id": batch.error_file_id,
            }

        time.sleep(poll_interval)


def download_batch_results(output_file_id: str, api_key: str, output_path: Path) -> None:
    """Download batch results to file."""
    client = OpenAI(api_key=api_key)
    content = client.files.content(output_file_id)

    with open(output_path, "wb") as f:
        f.write(content.read())


def parse_batch_results(results_path: Path) -> dict[str, LLMResult]:
    """
    Parse batch results file into chapter_id -> LLMResult mapping.
    """
    results = {}

    with open(results_path) as f:
        for line in f:
            if not line.strip():
                continue

            result = json.loads(line)
            chapter_id = result["custom_id"]

            if result.get("error"):
                results[chapter_id] = LLMResult(
                    stories=[],
                    input_tokens=0,
                    output_tokens=0,
                    duration_ms=0,
                    status="error",
                    error=str(result["error"]),
                )
            else:
                response = result["response"]
                body = response["body"]

                # Extract stories from response
                content = body["choices"][0]["message"]["content"]
                stories = json.loads(content)

                # Process story IDs
                processed_stories = []
                for story in stories:
                    if story.get("story_id") == "auto_or_uuid":
                        story["story_id"] = str(uuid.uuid4())
                    processed_stories.append(story)

                usage = body.get("usage", {})

                results[chapter_id] = LLMResult(
                    stories=processed_stories,
                    input_tokens=usage.get("prompt_tokens", 0),
                    output_tokens=usage.get("completion_tokens", 0),
                    duration_ms=0,  # Not available in batch
                    status="ok",
                )

    return results
