"""Database migration utilities for schema upgrades."""

import sqlite3
from pathlib import Path

from rich.console import Console

console = Console()


def get_schema_version(conn: sqlite3.Connection) -> str:
    """Get current schema version from books table."""
    try:
        cursor = conn.execute("SELECT schema_version FROM books LIMIT 1")
        row = cursor.fetchone()
        return row[0] if row else "1.0"
    except sqlite3.OperationalError:
        return "1.0"


def migrate_v1_0_to_v1_1(conn: sqlite3.Connection) -> None:
    """
    Migrate schema from v1.0 to v1.1.

    Adds geocoding resolution columns to story_locations table.
    """
    console.print("[cyan]Migrating schema from v1.0 to v1.1...[/cyan]")

    # Check if columns already exist
    cursor = conn.execute("PRAGMA table_info(story_locations)")
    columns = {row[1] for row in cursor.fetchall()}

    new_columns = [
        ("resolved_address", "TEXT"),
        ("resolved_lat", "REAL"),
        ("resolved_lon", "REAL"),
        ("resolved_precision", "TEXT"),
        ("resolution_confidence", "REAL"),
        ("resolution_source", "TEXT"),
        ("resolved_at", "TEXT"),
        ("resolution_hash", "TEXT"),
    ]

    for col_name, col_type in new_columns:
        if col_name not in columns:
            console.print(f"[dim]Adding column: {col_name}[/dim]")
            conn.execute(f"ALTER TABLE story_locations ADD COLUMN {col_name} {col_type}")

    # Create geocode_cache table if not exists
    conn.execute("""
        CREATE TABLE IF NOT EXISTS geocode_cache (
            url_hash    TEXT PRIMARY KEY,
            url         TEXT NOT NULL,
            title       TEXT,
            content     TEXT,
            fetched_at  TEXT DEFAULT (datetime('now')),
            expires_at  TEXT
        )
    """)

    conn.commit()
    console.print("[green]Migration to v1.1 complete![/green]")


def migrate_db(db_path: Path) -> None:
    """
    Run all necessary migrations to bring database to latest schema.
    """
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")

    current_version = get_schema_version(conn)
    console.print(f"[cyan]Current schema version: {current_version}[/cyan]")

    if current_version == "1.0":
        migrate_v1_0_to_v1_1(conn)
        # Update schema version in books table
        conn.execute("UPDATE books SET schema_version = '1.1'")
        conn.commit()
    elif current_version == "1.1":
        console.print("[green]Database is already at latest schema version (1.1)[/green]")
    else:
        console.print(f"[yellow]Warning: Unknown schema version {current_version}[/yellow]")

    conn.close()
