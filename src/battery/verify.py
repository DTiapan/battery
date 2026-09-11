"""Just-in-time verification of memory citations before recall."""

from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import pysqlite3 as sqlite3
except ImportError:
    import sqlite3

from battery.db import (
    get_citations_for_memory,
    hash_file_snippet,
    mark_memory_staleness,
    tombstone_memory,
)
from battery.migrate import log_memory_event


def verify_citation(citation: Dict[str, Any]) -> str:
    """
    Verifies a single citation against the filesystem.

    Returns 'valid', 'stale', or 'missing'.
    """
    file_path = Path(citation["file_path"])
    if not file_path.is_file():
        return "missing"

    stored_hash = citation.get("snippet_hash")
    if not stored_hash:
        return "valid"

    current_hash = hash_file_snippet(
        file_path,
        citation.get("line_start"),
        citation.get("line_end"),
    )
    if not current_hash:
        return "missing"
    if current_hash != stored_hash:
        return "stale"
    return "valid"


def verify_memory(conn: sqlite3.Connection, memory_id: int) -> str:
    """
    Verifies all citations for a memory.

    Returns aggregate status: 'valid', 'stale', or 'missing'.
    Memories without citations are always 'valid'.
    """
    row = conn.execute(
        "SELECT staleness, is_deleted FROM memories WHERE id = ?",
        (memory_id,),
    ).fetchone()
    if row is None or row["is_deleted"]:
        return "missing"

    citations = get_citations_for_memory(conn, memory_id)
    if not citations:
        return "valid"

    statuses = [verify_citation(c) for c in citations]
    if "missing" in statuses:
        aggregate = "missing"
    elif "stale" in statuses:
        aggregate = "stale"
    else:
        aggregate = "valid"

    if aggregate != row["staleness"]:
        mark_memory_staleness(conn, memory_id, aggregate)

    return aggregate


def filter_verified_results(
    conn: sqlite3.Connection,
    results: List[Dict[str, Any]],
    *,
    prune_on_fail: bool = False,
) -> List[Dict[str, Any]]:
    """Filters recall results to only verified memories; logs VERIFY_FAIL events."""
    verified: List[Dict[str, Any]] = []
    for record in results:
        memory_id = record["id"]
        status = verify_memory(conn, memory_id)
        if status == "valid":
            verified.append(record)
            continue

        log_memory_event(
            conn,
            "VERIFY_FAIL",
            memory_id,
            {"staleness": status, "content_preview": record.get("content", "")[:120]},
        )
        if prune_on_fail:
            tombstone_memory(conn, memory_id, reason=f"verify_{status}")

    conn.commit()
    return verified
