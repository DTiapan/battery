import hashlib
import struct
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure sqlite3 with extension loading support is available across platforms
sqlite3 = None
for _mod in ("pysqlite3", "sqlean"):
    try:
        sqlite3 = __import__(_mod)
        sys.modules["sqlite3"] = sqlite3
        break
    except ImportError:
        pass

if sqlite3 is None:
    import sqlite3

import sqlite_vec  # noqa: E402

from battery.config import DEFAULT_DB_PATH, EMBEDDING_DIM  # noqa: E402
from battery.migrate import log_memory_event, migrate_db  # noqa: E402

VALID_CATEGORIES = frozenset({"rule", "decision", "preference", "general", "episodic"})
VALID_SOURCES = frozenset({"manual", "hook", "mcp", "cli", "handoff", "git"})
VALID_STALENESS = frozenset({"valid", "stale", "missing"})


def serialize_vector(vector: List[float]) -> bytes:
    """Serializes a float list into raw float32 bytes for sqlite-vec."""
    return struct.pack(f"{len(vector)}f", *vector)


def get_connection(db_path: Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """Creates a connection with WAL mode and loads the sqlite-vec extension."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    if hasattr(conn, "enable_load_extension"):
        conn.enable_load_extension(True)
    sqlite_vec.load(conn)

    # Performance and concurrency pragmas
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA busy_timeout = 5000;")
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Initializes tables, FTS5 virtual index, vec0 vector table, and runs migrations."""
    with conn:
        # 1. Base storage table
        conn.execute("""
        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content_hash TEXT UNIQUE NOT NULL,
            content TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT 'general',
            importance REAL NOT NULL DEFAULT 1.0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            is_deleted INTEGER NOT NULL DEFAULT 0
        );
        """)

        # 2. Full-text search FTS5 index
        conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
            content,
            category,
            content=memories,
            content_rowid=id
        );
        """)

        # 3. Synchronize FTS5 with memories via triggers
        conn.execute("""
        CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
            INSERT INTO memories_fts(rowid, content, category)
            VALUES (new.id, new.content, new.category);
        END;
        """)

        conn.execute("""
        CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
            INSERT INTO memories_fts(memories_fts, rowid, content, category)
            VALUES ('delete', old.id, old.content, old.category);
        END;
        """)

        conn.execute("""
        CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
            INSERT INTO memories_fts(memories_fts, rowid, content, category)
            VALUES ('delete', old.id, old.content, old.category);
            INSERT INTO memories_fts(rowid, content, category)
            VALUES (new.id, new.content, new.category);
        END;
        """)

        # 4. Dense vector table
        conn.execute(f"""
        CREATE VIRTUAL TABLE IF NOT EXISTS vec_memories USING vec0(
            memory_id INTEGER PRIMARY KEY,
            embedding float[{EMBEDDING_DIM}] distance_metric=cosine
        );
        """)

    migrate_db(conn)


def hash_content(content: str) -> str:
    """Returns SHA-256 hex digest of normalized content."""
    return hashlib.sha256(content.strip().encode("utf-8")).hexdigest()


def hash_file_snippet(path: Path, line_start: Optional[int] = None, line_end: Optional[int] = None) -> str:
    """Returns SHA-256 of file content or a line range for citation verification."""
    if not path.is_file():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    if line_start is not None and line_end is not None:
        lines = text.splitlines()
        start = max(0, line_start - 1)
        end = min(len(lines), line_end)
        text = "\n".join(lines[start:end])
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def insert_citations(
    conn: sqlite3.Connection,
    memory_id: int,
    citations: List[Dict[str, Any]],
) -> int:
    """Inserts file citations for a memory. Returns count inserted."""
    inserted = 0
    for citation in citations:
        file_path = str(citation.get("file_path", "")).strip()
        if not file_path:
            continue
        line_start = citation.get("line_start")
        line_end = citation.get("line_end")
        snippet_hash = citation.get("snippet_hash")
        if not snippet_hash:
            path = Path(file_path)
            snippet_hash = hash_file_snippet(path, line_start, line_end) or None
        conn.execute(
            """
            INSERT OR IGNORE INTO memory_citations(
                memory_id, file_path, snippet_hash, line_start, line_end
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (memory_id, file_path, snippet_hash, line_start, line_end),
        )
        inserted += 1
    return inserted


def get_citations_for_memory(conn: sqlite3.Connection, memory_id: int) -> List[Dict[str, Any]]:
    """Returns all citations linked to a memory."""
    cursor = conn.execute(
        """
        SELECT id, memory_id, file_path, snippet_hash, line_start, line_end
        FROM memory_citations
        WHERE memory_id = ?
        """,
        (memory_id,),
    )
    return [dict(row) for row in cursor.fetchall()]


def insert_memory(
    conn: sqlite3.Connection,
    content: str,
    embedding: List[float],
    category: str = "general",
    importance: float = 1.0,
    source: str = "manual",
    session_id: Optional[str] = None,
    commit_sha: Optional[str] = None,
    citations: Optional[List[Dict[str, Any]]] = None,
    log_event: bool = True,
    near_dedup: bool = True,
    near_dedup_threshold: float | None = None,
) -> Dict[str, Any]:
    """Inserts a memory and its embedding, handling exact and near-duplicate deduplication."""
    from battery.config import NEAR_DUP_THRESHOLD as DEFAULT_NEAR_DUP_THRESHOLD
    from battery.dedup import find_near_duplicate, merge_near_duplicate

    threshold = (
        near_dedup_threshold if near_dedup_threshold is not None else DEFAULT_NEAR_DUP_THRESHOLD
    )
    content_clean = content.strip()
    c_hash = hash_content(content_clean)
    now = datetime.now(timezone.utc).isoformat()
    if category not in VALID_CATEGORIES:
        category = "general"
    if source not in VALID_SOURCES:
        source = "manual"

    with conn:
        cursor = conn.execute(
            "SELECT id, is_deleted FROM memories WHERE content_hash = ?", (c_hash,)
        )
        existing = cursor.fetchone()

        if existing:
            memory_id = existing["id"]
            if existing["is_deleted"]:
                conn.execute(
                    """
                    UPDATE memories
                    SET is_deleted = 0, category = ?, importance = ?, updated_at = ?,
                        source = ?, session_id = ?, commit_sha = ?,
                        staleness = 'valid', last_verified_at = ?
                    WHERE id = ?
                    """,
                    (
                        category,
                        importance,
                        now,
                        source,
                        session_id,
                        commit_sha,
                        now,
                        memory_id,
                    ),
                )
                vec_bytes = serialize_vector(embedding)
                conn.execute(
                    "INSERT OR REPLACE INTO vec_memories(memory_id, embedding) VALUES (?, ?)",
                    (memory_id, vec_bytes),
                )
                status = "restored"
            else:
                status = "existing"

            if citations:
                insert_citations(conn, memory_id, citations)

            result = {
                "id": memory_id,
                "content_hash": c_hash,
                "content": content_clean,
                "category": category,
                "importance": importance,
                "source": source,
                "status": status,
            }
            if log_event and status in ("created", "restored"):
                log_memory_event(
                    conn,
                    "ASSERT",
                    memory_id,
                    {"content_hash": c_hash, "category": category, "source": source},
                )
            return result

        if near_dedup and category in {"rule", "decision", "preference", "general"}:
            near_match = find_near_duplicate(
                conn,
                embedding,
                category=category,
                threshold=threshold,
            )
            if near_match:
                return merge_near_duplicate(
                    conn,
                    near_match["id"],
                    content_clean,
                    embedding,
                    category=category,
                    importance=importance,
                    source=source,
                    session_id=session_id,
                    commit_sha=commit_sha,
                    citations=citations,
                    similarity=near_match["similarity"],
                    log_event=log_event,
                )

        cursor = conn.execute(
            """
            INSERT INTO memories(
                content_hash, content, category, importance,
                created_at, updated_at, source, session_id, commit_sha,
                staleness, last_verified_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'valid', ?)
            """,
            (
                c_hash,
                content_clean,
                category,
                importance,
                now,
                now,
                source,
                session_id,
                commit_sha,
                now,
            ),
        )
        memory_id = cursor.lastrowid

        vec_bytes = serialize_vector(embedding)
        conn.execute(
            "INSERT INTO vec_memories(memory_id, embedding) VALUES (?, ?)",
            (memory_id, vec_bytes),
        )

        if citations:
            insert_citations(conn, memory_id, citations)

        if log_event:
            log_memory_event(
                conn,
                "ASSERT",
                memory_id,
                {"content_hash": c_hash, "category": category, "source": source},
            )

        return {
            "id": memory_id,
            "content_hash": c_hash,
            "content": content_clean,
            "category": category,
            "importance": importance,
            "source": source,
            "status": "created",
        }


def insert_memories_batch(
    conn: sqlite3.Connection,
    items: List[Dict[str, Any]],
) -> int:
    """Inserts a batch of memories and embeddings in a single atomic SQLite transaction."""
    if not items:
        return 0

    inserted_count = 0
    for item in items:
        embedding = item.get("embedding")
        if not embedding:
            continue
        result = insert_memory(
            conn,
            item["content"],
            embedding,
            category=item.get("category", "general"),
            importance=item.get("importance", 1.0),
            source=item.get("source", "manual"),
            log_event=False,
        )
        if result["status"] in ("created", "restored"):
            inserted_count += 1

    return inserted_count


def mark_memory_staleness(
    conn: sqlite3.Connection,
    memory_id: int,
    staleness: str,
) -> None:
    """Updates staleness status for a memory."""
    if staleness not in VALID_STALENESS:
        staleness = "stale"
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        UPDATE memories SET staleness = ?, last_verified_at = ?, updated_at = ?
        WHERE id = ?
        """,
        (staleness, now, now, memory_id),
    )


def tombstone_memory(conn: sqlite3.Connection, memory_id: int, reason: str = "manual") -> bool:
    """Marks a memory as deleted without removing historical audit trail."""
    now = datetime.now(timezone.utc).isoformat()
    with conn:
        cursor = conn.execute(
            "UPDATE memories SET is_deleted = 1, updated_at = ? WHERE id = ? AND is_deleted = 0",
            (now, memory_id),
        )
        if cursor.rowcount > 0:
            conn.execute("DELETE FROM vec_memories WHERE memory_id = ?", (memory_id,))
            log_memory_event(conn, "TOMBSTONE", memory_id, {"reason": reason})
            return True
        return False


def list_memories(
    conn: sqlite3.Connection,
    category: Optional[str] = None,
    include_deleted: bool = False,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """Lists memories chronologically with optional category filter."""
    query = """
        SELECT id, content, category, importance, created_at, updated_at,
               is_deleted, source, session_id, staleness
        FROM memories WHERE 1=1
    """
    params: List[Any] = []

    if not include_deleted:
        query += " AND is_deleted = 0"
    if category:
        query += " AND category = ?"
        params.append(category)

    query += " ORDER BY id DESC LIMIT ?"
    params.append(limit)

    cursor = conn.execute(query, params)
    return [dict(row) for row in cursor.fetchall()]


def memory_exists_for_commit(conn: sqlite3.Connection, commit_sha: str) -> bool:
    """Returns True if an active memory already references this commit SHA."""
    if not commit_sha:
        return False
    row = conn.execute(
        """
        SELECT 1 FROM memories
        WHERE commit_sha = ? AND is_deleted = 0
        LIMIT 1
        """,
        (commit_sha,),
    ).fetchone()
    return row is not None


def insert_session_checkpoint(
    conn: sqlite3.Connection,
    session_id: str,
    event_type: str,
    payload: Dict[str, Any],
    project_root: Optional[str] = None,
    memory_id: Optional[int] = None,
) -> int:
    """Persists a session checkpoint record."""
    import json

    now = datetime.now(timezone.utc).isoformat()
    cursor = conn.execute(
        """
        INSERT INTO session_checkpoints(
            session_id, event_type, project_root, payload_json, memory_id, created_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (session_id, event_type, project_root, json.dumps(payload), memory_id, now),
    )
    checkpoint_id = int(cursor.lastrowid)
    log_memory_event(
        conn,
        "CHECKPOINT",
        memory_id,
        {"checkpoint_id": checkpoint_id, "session_id": session_id, "event_type": event_type},
    )
    return checkpoint_id


def list_session_checkpoints(
    conn: sqlite3.Connection,
    project_root: Optional[str] = None,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """Lists recent session checkpoints, optionally filtered by project root."""
    import json

    query = """
        SELECT id, session_id, event_type, project_root, payload_json, memory_id, created_at
        FROM session_checkpoints
    """
    params: List[Any] = []
    if project_root:
        query += " WHERE project_root = ?"
        params.append(project_root)
    query += " ORDER BY id DESC LIMIT ?"
    params.append(limit)

    rows = []
    for row in conn.execute(query, params).fetchall():
        record = dict(row)
        record["payload"] = json.loads(record.pop("payload_json"))
        rows.append(record)
    return rows
