"""Semantic near-duplicate detection and merge on memory save."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

try:
    import pysqlite3 as sqlite3
except ImportError:
    import sqlite3

from battery.config import NEAR_DUP_THRESHOLD
from battery.db import hash_content, insert_citations, serialize_vector
from battery.migrate import log_memory_event

NEAR_DEDUP_CATEGORIES = frozenset({"rule", "decision", "preference", "general"})


def find_near_duplicate(
    conn: sqlite3.Connection,
    embedding: List[float],
    *,
    category: Optional[str] = None,
    threshold: float = NEAR_DUP_THRESHOLD,
    exclude_id: Optional[int] = None,
    top_k: int = 5,
) -> Optional[Dict[str, Any]]:
    """
    Finds the closest active memory by cosine similarity.

    Returns the best match when similarity >= threshold, else None.
    """
    query_bytes = serialize_vector(embedding)
    sql = """
        SELECT v.memory_id, v.distance, m.content, m.category
        FROM vec_memories v
        JOIN memories m ON m.id = v.memory_id
        WHERE v.embedding MATCH ? AND k = ?
          AND m.is_deleted = 0
          AND m.staleness = 'valid'
    """
    params: List[Any] = [query_bytes, top_k]
    if category:
        sql += " AND m.category = ?"
        params.append(category)
    if exclude_id is not None:
        sql += " AND m.id != ?"
        params.append(exclude_id)
    sql += " ORDER BY v.distance ASC LIMIT ?"
    params.append(top_k)

    cursor = conn.execute(sql, params)
    best: Optional[Dict[str, Any]] = None
    for row in cursor.fetchall():
        similarity = 1.0 - float(row["distance"])
        if similarity >= threshold:
            candidate = {
                "id": int(row["memory_id"]),
                "similarity": round(similarity, 4),
                "content": row["content"],
                "category": row["category"],
            }
            if best is None or candidate["similarity"] > best["similarity"]:
                best = candidate
    return best


def merge_near_duplicate(
    conn: sqlite3.Connection,
    memory_id: int,
    content: str,
    embedding: List[float],
    *,
    category: str,
    importance: float,
    source: str,
    session_id: Optional[str] = None,
    commit_sha: Optional[str] = None,
    citations: Optional[List[Dict[str, Any]]] = None,
    similarity: float,
    log_event: bool = True,
) -> Dict[str, Any]:
    """Updates an existing memory instead of inserting a near-duplicate row."""
    content_clean = content.strip()
    c_hash = hash_content(content_clean)
    now = datetime.now(timezone.utc).isoformat()

    conn.execute(
        """
        UPDATE memories
        SET content = ?, content_hash = ?, category = ?, importance = ?,
            updated_at = ?, source = ?, session_id = ?, commit_sha = ?,
            staleness = 'valid', last_verified_at = ?
        WHERE id = ? AND is_deleted = 0
        """,
        (
            content_clean,
            c_hash,
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
    conn.execute("DELETE FROM vec_memories WHERE memory_id = ?", (memory_id,))
    conn.execute(
        "INSERT INTO vec_memories(memory_id, embedding) VALUES (?, ?)",
        (memory_id, vec_bytes),
    )

    if citations:
        insert_citations(conn, memory_id, citations)

    if log_event:
        log_memory_event(
            conn,
            "MERGE",
            memory_id,
            {
                "reason": "near_duplicate",
                "similarity": similarity,
                "category": category,
                "source": source,
            },
        )

    return {
        "id": memory_id,
        "similarTo": memory_id,
        "content_hash": c_hash,
        "content": content_clean,
        "category": category,
        "importance": importance,
        "source": source,
        "status": "merged",
        "similarity": round(similarity, 4),
    }
