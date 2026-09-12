"""Git post-commit capture for episodic commit memories."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Dict, Optional

try:
    import pysqlite3 as sqlite3
except ImportError:
    import sqlite3

from battery.db import insert_memory, memory_exists_for_commit
from battery.embeddings import embed_text
from battery.migrate import log_memory_event

BATTERY_GIT_MARKER = "battery-context-engine-git"
MAX_FILES_IN_MEMORY = 25


def is_git_repo(project_root: Path) -> bool:
    """Returns True if project_root is inside a git work tree."""
    try:
        result = subprocess.run(
            ["git", "-C", str(project_root), "rev-parse", "--git-dir"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _run_git(project_root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(project_root), *args],
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode != 0:
        stderr = (result.stderr or result.stdout or "git command failed").strip()
        raise RuntimeError(stderr)
    return result.stdout.strip()


def get_commit_info(project_root: Path, commit_sha: Optional[str] = None) -> Dict[str, Any]:
    """Reads metadata for HEAD or a specific commit."""
    root = project_root.resolve()
    sha = commit_sha or _run_git(root, "rev-parse", "HEAD")
    short_sha = sha[:7] if len(sha) >= 7 else sha
    subject = _run_git(root, "log", "-1", "--pretty=format:%s", sha)
    body = _run_git(root, "log", "-1", "--pretty=format:%b", sha)
    author = _run_git(root, "log", "-1", "--pretty=format:%an", sha)

    files_raw = _run_git(root, "show", "--name-only", "--pretty=format:", sha)
    files = [line.strip() for line in files_raw.splitlines() if line.strip()]

    stat_line = _run_git(root, "show", "--stat", "--format=", sha)
    stat_summary = _summarize_stat(stat_line)

    return {
        "sha": sha,
        "short_sha": short_sha,
        "subject": subject,
        "body": body.strip(),
        "author": author,
        "files": files,
        "stat_summary": stat_summary,
        "stat_raw": stat_line.strip(),
    }


def _summarize_stat(stat_text: str) -> str:
    """Extracts the final summary line from git show --stat output."""
    lines = [line.strip() for line in stat_text.splitlines() if line.strip()]
    if not lines:
        return "0 files changed"
    last = lines[-1]
    if "changed" in last or "insertion" in last or "deletion" in last:
        return last
    return f"{len(lines)} files listed"


def format_commit_memory(info: Dict[str, Any]) -> str:
    """Formats commit metadata as searchable episodic text."""
    lines = [f"Commit {info['short_sha']}: {info['subject']}"]
    if info.get("body"):
        lines.append(info["body"])
    if info.get("stat_summary"):
        lines.append(f"Diff stat: {info['stat_summary']}")
    files = info.get("files") or []
    if files:
        shown = files[:MAX_FILES_IN_MEMORY]
        lines.append("Changed files: " + ", ".join(shown))
        if len(files) > len(shown):
            lines.append(f"(+{len(files) - len(shown)} more files)")
    return "\n".join(lines)


def capture_commit(
    conn: sqlite3.Connection,
    project_root: Path,
    *,
    commit_sha: Optional[str] = None,
) -> Dict[str, Any]:
    """Captures the latest (or specified) git commit as episodic memory."""
    root = project_root.resolve()
    if not is_git_repo(root):
        raise ValueError(f"Not a git repository: {root}")

    info = get_commit_info(root, commit_sha=commit_sha)
    if memory_exists_for_commit(conn, info["sha"]):
        return {
            "status": "existing",
            "commit_sha": info["sha"],
            "short_sha": info["short_sha"],
        }

    content = format_commit_memory(info)
    vec = embed_text(content)
    citations = [{"file_path": path} for path in info["files"][:MAX_FILES_IN_MEMORY]]

    result = insert_memory(
        conn,
        content,
        vec,
        category="episodic",
        importance=0.6,
        source="git",
        commit_sha=info["sha"],
        citations=citations or None,
    )

    log_memory_event(
        conn,
        "GIT_COMMIT",
        result["id"],
        {
            "commit_sha": info["sha"],
            "files": len(info["files"]),
            "subject": info["subject"],
        },
    )

    return {
        "status": result["status"],
        "memory_id": result["id"],
        "commit_sha": info["sha"],
        "short_sha": info["short_sha"],
        "subject": info["subject"],
        "files": len(info["files"]),
    }
