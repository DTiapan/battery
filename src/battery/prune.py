"""Batch stale memory detection and pruning."""

import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

try:
    import pysqlite3 as sqlite3
except ImportError:
    import sqlite3

from battery.db import get_citations_for_memory, tombstone_memory
from battery.migrate import log_memory_event
from battery.verify import verify_memory


def _git_deleted_files(project_root: Path, since_commit: Optional[str] = None) -> Set[str]:
    """Returns file paths deleted in git history under project_root."""
    if not (project_root / ".git").is_dir():
        return set()

    cmd = ["git", "-C", str(project_root), "log", "--diff-filter=D", "--name-only", "--pretty=format:"]
    if since_commit:
        cmd.append(f"{since_commit}..HEAD")

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=30)
    except (subprocess.SubprocessError, OSError):
        return set()

    if result.returncode != 0:
        return set()

    deleted: Set[str] = set()
    for line in result.stdout.splitlines():
        path = line.strip()
        if path:
            deleted.add(path)
    return deleted


def find_stale_memories(
    conn: sqlite3.Connection,
    project_root: Optional[Path] = None,
    since_commit: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Finds active memories with invalid or stale citations."""
    cursor = conn.execute(
        """
        SELECT DISTINCT m.id, m.content, m.category, m.staleness
        FROM memories m
        JOIN memory_citations c ON c.memory_id = m.id
        WHERE m.is_deleted = 0
        """
    )
    candidates = [dict(row) for row in cursor.fetchall()]

    git_deleted: Set[str] = set()
    if project_root:
        git_deleted = _git_deleted_files(project_root.resolve(), since_commit)

    stale: List[Dict[str, Any]] = []
    for memory in candidates:
        memory_id = memory["id"]
        citations = get_citations_for_memory(conn, memory_id)

        for citation in citations:
            rel_path = citation["file_path"]
            if git_deleted and rel_path in git_deleted:
                memory["reason"] = "git_deleted"
                stale.append(memory)
                break

        if memory in stale:
            continue

        status = verify_memory(conn, memory_id)
        if status != "valid":
            memory["reason"] = status
            stale.append(memory)

    return stale


def prune_stale_memories(
    conn: sqlite3.Connection,
    project_root: Optional[Path] = None,
    since_commit: Optional[str] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Tombstones memories with stale or missing citations."""
    stale = find_stale_memories(conn, project_root=project_root, since_commit=since_commit)
    pruned_ids: List[int] = []

    with conn:
        for memory in stale:
            memory_id = memory["id"]
            if dry_run:
                pruned_ids.append(memory_id)
                continue
            if tombstone_memory(conn, memory_id, reason=memory.get("reason", "prune")):
                pruned_ids.append(memory_id)
                log_memory_event(
                    conn,
                    "PRUNE",
                    memory_id,
                    {"reason": memory.get("reason"), "dry_run": False},
                )

    return {
        "dry_run": dry_run,
        "candidates": len(stale),
        "pruned_ids": pruned_ids,
        "memories": stale,
    }
