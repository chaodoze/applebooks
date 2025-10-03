"""SQLite database schema and management."""

import sqlite3
from pathlib import Path

SCHEMA_VERSION = "1.1"


def _migrate_v1_0_to_v1_1(conn: sqlite3.Connection):
    """Migrate database schema from v1.0 to v1.1 (add geocoding columns)."""
    # Add new columns to story_locations
    conn.execute("ALTER TABLE story_locations ADD COLUMN resolved_address TEXT")
    conn.execute("ALTER TABLE story_locations ADD COLUMN resolved_lat REAL")
    conn.execute("ALTER TABLE story_locations ADD COLUMN resolved_lon REAL")
    conn.execute("ALTER TABLE story_locations ADD COLUMN resolved_precision TEXT")
    conn.execute("ALTER TABLE story_locations ADD COLUMN resolution_confidence REAL")
    conn.execute("ALTER TABLE story_locations ADD COLUMN resolution_source TEXT")
    conn.execute("ALTER TABLE story_locations ADD COLUMN resolved_at TEXT")
    conn.execute("ALTER TABLE story_locations ADD COLUMN resolution_hash TEXT")

    # Create geocode_cache table
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

    # Add indexes
    conn.execute("CREATE INDEX IF NOT EXISTS idx_story_locations_resolution_hash ON story_locations(resolution_hash)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_story_locations_resolved_at ON story_locations(resolved_at)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_story_locations_resolution_confidence ON story_locations(resolution_confidence)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_geocode_cache_expires_at ON geocode_cache(expires_at)")

    conn.commit()


def init_db(db_path: Path) -> sqlite3.Connection:
    """Initialize database with schema and FTS tables."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")

    # Get current schema version from database
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='books'")
    db_exists = cursor.fetchone() is not None

    if db_exists:
        cursor = conn.execute("PRAGMA table_info(story_locations)")
        columns = {row[1] for row in cursor.fetchall()}

        # Migrate from v1.0 to v1.1 if needed
        if "resolved_address" not in columns:
            _migrate_v1_0_to_v1_1(conn)

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
            resolved_address TEXT,
            resolved_lat   REAL,
            resolved_lon   REAL,
            resolved_precision TEXT,
            resolution_confidence REAL,
            resolution_source TEXT,
            resolved_at    TEXT,
            resolution_hash TEXT,
            PRIMARY KEY(story_id, loc_idx),
            FOREIGN KEY(story_id) REFERENCES stories(story_id) ON DELETE CASCADE
        )
    """)
    # Add index on story_id for faster JOINs and CASCADE deletes
    conn.execute("CREATE INDEX IF NOT EXISTS idx_story_locations_story_id ON story_locations(story_id)")

    # Geocoding cache (7-day URL cache)
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

    # Indexes for geocoding columns (only if not already created by migration)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_story_locations_resolution_hash ON story_locations(resolution_hash)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_story_locations_resolved_at ON story_locations(resolved_at)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_story_locations_resolution_confidence ON story_locations(resolution_confidence)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_geocode_cache_expires_at ON geocode_cache(expires_at)")

    # Trigger for automatic geocode cache cleanup
    # Limit to 100 rows per cleanup to avoid table locking on large caches
    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS geocode_cache_cleanup
        AFTER INSERT ON geocode_cache
        BEGIN
            DELETE FROM geocode_cache
            WHERE url_hash IN (
                SELECT url_hash FROM geocode_cache
                WHERE expires_at IS NOT NULL
                  AND datetime(expires_at) < datetime('now')
                LIMIT 100
            );
        END
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
