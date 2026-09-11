import hashlib
import struct
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
import sqlite_vec

try:
    import pysqlite3 as sqlite3
except ImportError:
    import sqlite3

from battery.config import DEFAULT_DB_PATH, EMBEDDING_DIM

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
    """Initializes tables, FTS5 virtual index, and vec0 vector virtual table."""
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

def hash_content(content: str) -> str:
    """Returns SHA-256 hex digest of normalized content."""
    return hashlib.sha256(content.strip().encode("utf-8")).hexdigest()

def insert_memory(
    conn: sqlite3.Connection,
    content: str,
    embedding: List[float],
    category: str = "general",
    importance: float = 1.0,
) -> Dict[str, Any]:
    """Inserts a memory and its embedding, handling content deduplication."""
    content_clean = content.strip()
    c_hash = hash_content(content_clean)
    now = datetime.now(timezone.utc).isoformat()
    
    with conn:
        cursor = conn.execute(
            "SELECT id, is_deleted FROM memories WHERE content_hash = ?",
            (c_hash,)
        )
        existing = cursor.fetchone()
        
        if existing:
            memory_id = existing["id"]
            if existing["is_deleted"]:
                # Undelete and update timestamp
                conn.execute(
                    "UPDATE memories SET is_deleted = 0, category = ?, importance = ?, updated_at = ? WHERE id = ?",
                    (category, importance, now, memory_id)
                )
                vec_bytes = serialize_vector(embedding)
                conn.execute(
                    "INSERT OR REPLACE INTO vec_memories(memory_id, embedding) VALUES (?, ?)",
                    (memory_id, vec_bytes)
                )
            return {
                "id": memory_id,
                "content_hash": c_hash,
                "content": content_clean,
                "category": category,
                "importance": importance,
                "status": "existing" if not existing["is_deleted"] else "restored",
            }
        
        # Insert new record
        cursor = conn.execute(
            """
            INSERT INTO memories(content_hash, content, category, importance, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (c_hash, content_clean, category, importance, now, now)
        )
        memory_id = cursor.lastrowid
        
        # Insert into vector virtual table
        vec_bytes = serialize_vector(embedding)
        conn.execute(
            "INSERT INTO vec_memories(memory_id, embedding) VALUES (?, ?)",
            (memory_id, vec_bytes)
        )
        
        return {
            "id": memory_id,
            "content_hash": c_hash,
            "content": content_clean,
            "category": category,
            "importance": importance,
            "status": "created",
        }

def tombstone_memory(conn: sqlite3.Connection, memory_id: int) -> bool:
    """Marks a memory as deleted without removing historical audit trail."""
    now = datetime.now(timezone.utc).isoformat()
    with conn:
        cursor = conn.execute(
            "UPDATE memories SET is_deleted = 1, updated_at = ? WHERE id = ? AND is_deleted = 0",
            (now, memory_id)
        )
        if cursor.rowcount > 0:
            # Delete from vec_memories to prevent it matching in vector searches
            conn.execute("DELETE FROM vec_memories WHERE memory_id = ?", (memory_id,))
            return True
        return False

def list_memories(
    conn: sqlite3.Connection,
    category: Optional[str] = None,
    include_deleted: bool = False,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """Lists memories chronologically with optional category filter."""
    query = "SELECT id, content, category, importance, created_at, updated_at, is_deleted FROM memories WHERE 1=1"
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
