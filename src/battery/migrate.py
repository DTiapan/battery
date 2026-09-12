"""Schema versioning and migrations for Battery SQLite databases."""

import json
import sqlite3
from datetime import datetime, timezone
from typing import List

SCHEMA_VERSION = 2

_MEMORY_V2_COLUMNS = (
    ("source", "TEXT NOT NULL DEFAULT 'manual'"),
    ("session_id", "TEXT"),
    ("commit_sha", "TEXT"),
    ("staleness", "TEXT NOT NULL DEFAULT 'valid'"),
    ("last_verified_at", "TEXT"),
)


def get_schema_version(conn: sqlite3.Connection) -> int:
    """Returns the current schema version, or 0 if uninitialized."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        """
    )
    row = conn.execute("SELECT value FROM schema_meta WHERE key = 'schema_version'").fetchone()
    if row is None:
        return 0
    try:
        return int(row[0])
    except (TypeError, ValueError):
        return 0


def _set_schema_version(conn: sqlite3.Connection, version: int) -> None:
    conn.execute(
        """
        INSERT INTO schema_meta(key, value) VALUES ('schema_version', ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (str(version),),
    )


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (name,),
    ).fetchone()
    return row is not None


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r[1] == column for r in rows)


def _migrate_to_v2(conn: sqlite3.Connection) -> None:
    """Adds lifecycle columns, event log, citations, and session checkpoints."""
    for column, definition in _MEMORY_V2_COLUMNS:
        if not _column_exists(conn, "memories", column):
            conn.execute(f"ALTER TABLE memories ADD COLUMN {column} {definition}")

    if not _table_exists(conn, "memory_events"):
        conn.execute(
            """
            CREATE TABLE memory_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                memory_id INTEGER,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_memory_events_type ON memory_events(event_type);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_memory_events_memory_id ON memory_events(memory_id);"
        )

    if not _table_exists(conn, "memory_citations"):
        conn.execute(
            """
            CREATE TABLE memory_citations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                memory_id INTEGER NOT NULL REFERENCES memories(id),
                file_path TEXT NOT NULL,
                snippet_hash TEXT,
                line_start INTEGER,
                line_end INTEGER,
                UNIQUE(memory_id, file_path, snippet_hash)
            );
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_memory_citations_memory_id "
            "ON memory_citations(memory_id);"
        )

    if not _table_exists(conn, "session_checkpoints"):
        conn.execute(
            """
            CREATE TABLE session_checkpoints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                project_root TEXT,
                payload_json TEXT NOT NULL,
                memory_id INTEGER,
                created_at TEXT NOT NULL
            );
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_session_checkpoints_session "
            "ON session_checkpoints(session_id);"
        )


def migrate_db(conn: sqlite3.Connection) -> int:
    """Applies pending migrations and returns the resulting schema version."""
    current = get_schema_version(conn)
    if current == 0 and _table_exists(conn, "memories"):
        current = 1
        _set_schema_version(conn, 1)

    migrations: List[tuple[int, callable]] = [
        (2, _migrate_to_v2),
    ]

    with conn:
        for target_version, migrate_fn in migrations:
            if current < target_version:
                migrate_fn(conn)
                _set_schema_version(conn, target_version)
                current = target_version

    return current


def log_memory_event(
    conn: sqlite3.Connection,
    event_type: str,
    memory_id: int | None,
    payload: dict,
) -> int:
    """Appends an event to the memory_events log."""
    now = datetime.now(timezone.utc).isoformat()
    cursor = conn.execute(
        """
        INSERT INTO memory_events(event_type, memory_id, payload_json, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (event_type, memory_id, json.dumps(payload), now),
    )
    return int(cursor.lastrowid)
