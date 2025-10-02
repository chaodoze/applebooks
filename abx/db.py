"""SQLite database schema and management."""

import sqlite3
from pathlib import Path

SCHEMA_VERSION = "1.0"


def init_db(db_path: Path) -> sqlite3.Connection:
    """Initialize database with schema and FTS tables."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")

    # Books
    conn.execute("""
        CREATE TABLE IF NOT EXISTS books (
            book_id        TEXT PRIMARY KEY,
            sha256         TEXT UNIQUE NOT NULL,
            title          TEXT,
            authors        TEXT,
            publisher      TEXT,
            published_date TEXT,
            language       TEXT,
            source_path    TEXT,
            schema_version TEXT,
            added_at       TEXT DEFAULT (datetime('now'))
        )
    """)

    # Chapters
    conn.execute("""
        CREATE TABLE IF NOT EXISTS chapters (
            chapter_id     TEXT PRIMARY KEY,
            book_id        TEXT NOT NULL,
            idx            INTEGER NOT NULL,
            title          TEXT,
            text_raw       TEXT,
            text_clean     TEXT,
            word_count     INTEGER,
            href           TEXT,
            UNIQUE(book_id, idx),
            FOREIGN KEY(book_id) REFERENCES books(book_id) ON DELETE CASCADE
        )
    """)

    # FTS for chapters
    conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS chapter_fts USING fts5(
            chapter_id, book_id, title, text_raw, content='chapters', content_rowid='rowid'
        )
    """)

    # FTS triggers
    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS chapter_fts_insert AFTER INSERT ON chapters BEGIN
            INSERT INTO chapter_fts(rowid, chapter_id, book_id, title, text_raw)
            VALUES (new.rowid, new.chapter_id, new.book_id, new.title, new.text_raw);
        END
    """)

    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS chapter_fts_update AFTER UPDATE ON chapters BEGIN
            UPDATE chapter_fts SET chapter_id=new.chapter_id, book_id=new.book_id,
                                   title=new.title, text_raw=new.text_raw
            WHERE rowid=old.rowid;
        END
    """)

    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS chapter_fts_delete AFTER DELETE ON chapters BEGIN
            DELETE FROM chapter_fts WHERE rowid=old.rowid;
        END
    """)

    # Stories
    conn.execute("""
        CREATE TABLE IF NOT EXISTS stories (
            story_id       TEXT PRIMARY KEY,
            chapter_id     TEXT NOT NULL,
            story_json     TEXT NOT NULL,
            title          TEXT,
            summary        TEXT,
            event_types_json TEXT,
            themes_json      TEXT,
            tone_json        TEXT,
            confidence     REAL,
            parsed_date    TEXT,
            date_start     TEXT,
            date_end       TEXT,
            place_primary  TEXT,
            lat            REAL,
            lon            REAL,
            created_at     TEXT DEFAULT (datetime('now')),
            FOREIGN KEY(chapter_id) REFERENCES chapters(chapter_id) ON DELETE CASCADE
        )
    """)

    # FTS for stories
    conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS story_fts USING fts5(
            story_id, title, summary, content='stories', content_rowid='rowid'
        )
    """)

    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS story_fts_insert AFTER INSERT ON stories BEGIN
            INSERT INTO story_fts(rowid, story_id, title, summary)
            VALUES (new.rowid, new.story_id, new.title, new.summary);
        END
    """)

    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS story_fts_update AFTER UPDATE ON stories BEGIN
            UPDATE story_fts SET story_id=new.story_id, title=new.title, summary=new.summary
            WHERE rowid=old.rowid;
        END
    """)

    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS story_fts_delete AFTER DELETE ON stories BEGIN
            DELETE FROM story_fts WHERE rowid=old.rowid;
        END
    """)

    # Pivots
    conn.execute("""
        CREATE TABLE IF NOT EXISTS story_people (
            story_id     TEXT,
            person_idx   INTEGER,
            name         TEXT,
            role_at_time TEXT,
            team         TEXT,
            affiliation  TEXT,
            PRIMARY KEY(story_id, person_idx),
            FOREIGN KEY(story_id) REFERENCES stories(story_id) ON DELETE CASCADE
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS story_companies (
            story_id     TEXT,
            company_idx  INTEGER,
            name         TEXT,
            relationship TEXT,
            PRIMARY KEY(story_id, company_idx),
            FOREIGN KEY(story_id) REFERENCES stories(story_id) ON DELETE CASCADE
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS story_products (
            story_id        TEXT,
            product_idx     INTEGER,
            product_line    TEXT,
            model           TEXT,
            codename        TEXT,
            generation      TEXT,
            design_language TEXT,
            PRIMARY KEY(story_id, product_idx),
            FOREIGN KEY(story_id) REFERENCES stories(story_id) ON DELETE CASCADE
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS story_locations (
            story_id       TEXT,
            loc_idx        INTEGER,
            place_name     TEXT,
            lat            REAL,
            lon            REAL,
            place_type     TEXT,
            geo_precision  TEXT,
            visitability   TEXT,
            note           TEXT,
            is_forward_locale INTEGER DEFAULT 0,
            PRIMARY KEY(story_id, loc_idx),
            FOREIGN KEY(story_id) REFERENCES stories(story_id) ON DELETE CASCADE
        )
    """)

    # LLM runs
    conn.execute("""
        CREATE TABLE IF NOT EXISTS llm_runs (
            run_id        TEXT PRIMARY KEY,
            book_id       TEXT,
            schema_version TEXT,
            model         TEXT,
            prompt_hash   TEXT,
            baml_version  TEXT,
            created_at    TEXT DEFAULT (datetime('now')),
            batch_job_id  TEXT
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS chapter_llm (
            chapter_id    TEXT,
            run_id        TEXT,
            status        TEXT,
            input_tokens  INTEGER,
            output_tokens INTEGER,
            duration_ms   INTEGER,
            error         TEXT,
            PRIMARY KEY(chapter_id, run_id),
            FOREIGN KEY(chapter_id) REFERENCES chapters(chapter_id) ON DELETE CASCADE,
            FOREIGN KEY(run_id) REFERENCES llm_runs(run_id) ON DELETE CASCADE
        )
    """)

    conn.commit()
    return conn
