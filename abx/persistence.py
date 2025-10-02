"""Persistence layer for stories and metadata."""

import json
import sqlite3
import uuid
from typing import Any

from abx.db import SCHEMA_VERSION


def store_book(conn: sqlite3.Connection, book_id: str, metadata: dict[str, Any]) -> None:
    """Store book metadata."""
    conn.execute(
        """
        INSERT OR IGNORE INTO books
        (book_id, sha256, title, authors, publisher, published_date, language, source_path, schema_version)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            book_id,
            metadata["sha256"],
            metadata["title"],
            json.dumps(metadata["authors"]),
            metadata.get("publisher"),
            metadata.get("published_date"),
            metadata.get("language"),
            metadata["source_path"],
            SCHEMA_VERSION,
        ),
    )
    conn.commit()


def store_chapter(
    conn: sqlite3.Connection,
    chapter_id: str,
    book_id: str,
    idx: int,
    title: str,
    text_raw: str,
    text_clean: str,
    href: str,
) -> None:
    """Store chapter with raw and clean text."""
    word_count = len(text_clean.split())

    conn.execute(
        """
        INSERT OR REPLACE INTO chapters
        (chapter_id, book_id, idx, title, text_raw, text_clean, word_count, href)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (chapter_id, book_id, idx, title, text_raw, text_clean, word_count, href),
    )
    conn.commit()


def store_llm_run(
    conn: sqlite3.Connection,
    run_id: str,
    book_id: str,
    model: str,
    prompt_hash: str,
    baml_version: str,
    batch_job_id: str | None = None,
) -> None:
    """Store LLM run metadata."""
    conn.execute(
        """
        INSERT INTO llm_runs
        (run_id, book_id, schema_version, model, prompt_hash, baml_version, batch_job_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (run_id, book_id, SCHEMA_VERSION, model, prompt_hash, baml_version, batch_job_id),
    )
    conn.commit()


def store_chapter_llm_result(
    conn: sqlite3.Connection,
    chapter_id: str,
    run_id: str,
    status: str,
    input_tokens: int,
    output_tokens: int,
    duration_ms: int,
    error: str | None = None,
) -> None:
    """Store LLM result for a chapter."""
    conn.execute(
        """
        INSERT OR REPLACE INTO chapter_llm
        (chapter_id, run_id, status, input_tokens, output_tokens, duration_ms, error)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (chapter_id, run_id, status, input_tokens, output_tokens, duration_ms, error),
    )
    conn.commit()


def store_stories(conn: sqlite3.Connection, chapter_id: str, stories: list[dict[str, Any]]) -> None:
    """Store stories and pivot tables."""
    for story in stories:
        story_id = story.get("story_id", str(uuid.uuid4()))

        # Extract indexed fields
        event_types_json = json.dumps(story.get("event_type", []))
        themes_json = json.dumps(story.get("themes", []))
        tone_json = json.dumps(story.get("tone", []))
        confidence = story.get("confidence", 0.5)

        # Date parsing
        dates = story.get("dates", {})
        parsed_date = dates.get("parsed") if dates else None
        date_start, date_end = parse_date_range(parsed_date) if parsed_date else (None, None)

        # Primary location
        locations = story.get("locations", [])
        place_primary = None
        lat, lon = None, None
        if locations:
            place_primary = locations[0].get("place_name")
            lat = locations[0].get("lat")
            lon = locations[0].get("lon")

        # Store main story record
        conn.execute(
            """
            INSERT OR REPLACE INTO stories
            (story_id, chapter_id, story_json, title, summary, event_types_json, themes_json,
             tone_json, confidence, parsed_date, date_start, date_end, place_primary, lat, lon)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                story_id,
                chapter_id,
                json.dumps(story),
                story.get("title"),
                story.get("summary"),
                event_types_json,
                themes_json,
                tone_json,
                confidence,
                parsed_date,
                date_start,
                date_end,
                place_primary,
                lat,
                lon,
            ),
        )

        # Store people
        for idx, person in enumerate(story.get("people") or []):
            conn.execute(
                """
                INSERT OR REPLACE INTO story_people
                (story_id, person_idx, name, role_at_time, team, affiliation)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    story_id,
                    idx,
                    person.get("name"),
                    person.get("role_at_time"),
                    person.get("team"),
                    person.get("affiliation"),
                ),
            )

        # Store companies
        for idx, company in enumerate(story.get("companies") or []):
            conn.execute(
                """
                INSERT OR REPLACE INTO story_companies
                (story_id, company_idx, name, relationship)
                VALUES (?, ?, ?, ?)
                """,
                (story_id, idx, company.get("name"), company.get("relationship")),
            )

        # Store products
        for idx, product in enumerate(story.get("products") or []):
            conn.execute(
                """
                INSERT OR REPLACE INTO story_products
                (story_id, product_idx, product_line, model, codename, generation, design_language)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    story_id,
                    idx,
                    product.get("product_line"),
                    product.get("model"),
                    product.get("codename"),
                    product.get("generation"),
                    product.get("design_language"),
                ),
            )

        # Store locations
        for idx, location in enumerate(story.get("locations") or []):
            conn.execute(
                """
                INSERT OR REPLACE INTO story_locations
                (story_id, loc_idx, place_name, lat, lon, place_type, geo_precision, visitability, note, is_forward_locale)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                """,
                (
                    story_id,
                    idx,
                    location.get("place_name"),
                    location.get("lat"),
                    location.get("lon"),
                    location.get("place_type"),
                    location.get("geo_precision"),
                    location.get("visitability"),
                    location.get("note"),
                ),
            )

        # Store forward_locale
        forward_locale = story.get("forward_locale")
        if forward_locale:
            conn.execute(
                """
                INSERT OR REPLACE INTO story_locations
                (story_id, loc_idx, place_name, lat, lon, place_type, geo_precision, visitability, note, is_forward_locale)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                """,
                (
                    story_id,
                    9999,  # Use high index for forward_locale
                    forward_locale.get("place_name"),
                    forward_locale.get("lat"),
                    forward_locale.get("lon"),
                    forward_locale.get("place_type"),
                    forward_locale.get("geo_precision"),
                    forward_locale.get("visitability"),
                    forward_locale.get("note"),
                ),
            )

    conn.commit()


def parse_date_range(parsed_date: str) -> tuple[str | None, str | None]:
    """
    Parse EDTF-ish date into start/end range for sorting.

    Examples:
        "1984" -> ("1984-01-01", "1984-12-31")
        "1984-03" -> ("1984-03-01", "1984-03-31")
        "1984-03~" -> ("1984-03-01", "1984-03-31")  # fuzzy
        "1984-03-15" -> ("1984-03-15", "1984-03-15")
    """
    if not parsed_date:
        return None, None

    # Strip fuzzy markers
    clean_date = parsed_date.rstrip("~?")

    parts = clean_date.split("-")

    if len(parts) == 1:  # Year only
        year = parts[0]
        return f"{year}-01-01", f"{year}-12-31"
    elif len(parts) == 2:  # Year-month
        year, month = parts
        # Approximate end day (good enough for sorting)
        return f"{year}-{month}-01", f"{year}-{month}-28"
    elif len(parts) == 3:  # Year-month-day
        return clean_date, clean_date

    return None, None


def check_idempotency(conn: sqlite3.Connection, book_sha: str, model: str, prompt_hash: str) -> str | None:
    """
    Check if this extraction has already been run.

    Returns run_id if found, None otherwise.
    """
    cursor = conn.execute(
        """
        SELECT r.run_id
        FROM llm_runs r
        JOIN books b ON r.book_id = b.book_id
        WHERE b.sha256 = ? AND r.model = ? AND r.prompt_hash = ? AND r.schema_version = ?
        """,
        (book_sha, model, prompt_hash, SCHEMA_VERSION),
    )
    row = cursor.fetchone()
    return row[0] if row else None
