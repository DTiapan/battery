"""Cross-tool session handoff export and load."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import pysqlite3 as sqlite3
except ImportError:
    import sqlite3

from battery.checkpoint import _checkpoint_content
from battery.db import insert_memory, list_memories, list_session_checkpoints
from battery.embeddings import embed_text
from battery.migrate import log_memory_event
from battery.sync import export_battery_md

HANDOFF_VERSION = 1
HANDOFF_JSON = "HANDOFF.json"
HANDOFF_MD = "HANDOFF.md"
LINEAGE_FILE = "lineage.jsonl"


def get_handoff_dir(project_root: Optional[Path] = None) -> Path:
    """Returns the project-local handoff directory."""
    root = Path(project_root or Path.cwd()).resolve()
    return root / ".battery" / "handoff"


def verify_changed_files(
    changed_files: List[str],
    project_root: Path,
) -> Dict[str, Any]:
    """Checks whether handoff changed_files still exist on disk."""
    valid: List[str] = []
    missing: List[str] = []
    for raw in changed_files:
        path = Path(raw)
        if not path.is_absolute():
            path = project_root / path
        if path.is_file():
            valid.append(raw)
        else:
            missing.append(raw)

    if not changed_files:
        status = "unknown"
    elif not missing:
        status = "valid"
    elif valid:
        status = "partial"
    else:
        status = "missing"

    return {
        "status": status,
        "valid_count": len(valid),
        "missing_count": len(missing),
        "valid": valid,
        "missing": missing,
    }


def _active_context_summary(conn: sqlite3.Connection, limit: int = 8) -> List[Dict[str, Any]]:
    """Returns recent active rules and decisions for handoff context."""
    items: List[Dict[str, Any]] = []
    for category in ("rule", "decision"):
        items.extend(list_memories(conn, category=category, limit=limit))
    items.sort(key=lambda row: row["id"], reverse=True)
    return items[:limit]


def _read_previous_lineage(handoff_dir: Path) -> List[Dict[str, Any]]:
    """Reads lineage from the previous handoff artifact, if any."""
    previous_path = handoff_dir / HANDOFF_JSON
    if not previous_path.is_file():
        return []
    try:
        previous = json.loads(previous_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []

    lineage = list(previous.get("lineage") or [])
    hop = {
        "handoff_id": previous.get("handoff_id"),
        "from_client": previous.get("from_client"),
        "to_client": previous.get("to_client"),
        "created_at": previous.get("created_at"),
    }
    if hop.get("handoff_id"):
        lineage.append(hop)
    return lineage[-10:]


def build_handoff_artifact(
    conn: sqlite3.Connection,
    *,
    project_root: Path,
    profile: str,
    from_client: str,
    to_client: Optional[str] = None,
    checkpoint_row: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Builds a structured handoff artifact from the latest checkpoint."""
    root = project_root.resolve()
    if checkpoint_row is None:
        rows = list_session_checkpoints(conn, project_root=str(root), limit=1)
        checkpoint_row = rows[0] if rows else None

    payload = (checkpoint_row or {}).get("payload") or {}
    changed_files = list(payload.get("changed_files") or [])
    verification = verify_changed_files(changed_files, root)
    handoff_dir = get_handoff_dir(root)
    lineage = _read_previous_lineage(handoff_dir)
    created_at = datetime.now(timezone.utc).isoformat()

    context_items = _active_context_summary(conn)
    artifact: Dict[str, Any] = {
        "version": HANDOFF_VERSION,
        "handoff_id": str(uuid.uuid4()),
        "created_at": created_at,
        "from_client": from_client,
        "to_client": to_client,
        "project_root": str(root),
        "profile": profile,
        "checkpoint_id": checkpoint_row["id"] if checkpoint_row else None,
        "session_id": payload.get("session_id") or (checkpoint_row or {}).get("session_id"),
        "event_type": payload.get("event_type") or (checkpoint_row or {}).get("event_type"),
        "task_summary": payload.get("task_summary") or "",
        "next_action": payload.get("next_step") or payload.get("next_action") or "",
        "decisions": list(payload.get("decisions") or []),
        "rejected_approaches": list(payload.get("rejected_approaches") or []),
        "blockers": list(payload.get("blockers") or []),
        "changed_files": changed_files,
        "verification_status": verification["status"],
        "verification": verification,
        "active_context": [
            {"id": item["id"], "category": item["category"], "content": item["content"]}
            for item in context_items
        ],
        "lineage": lineage,
    }

    if not checkpoint_row and not artifact["task_summary"]:
        latest_episodic = list_memories(conn, category="episodic", limit=1)
        if latest_episodic:
            artifact["task_summary"] = latest_episodic[0]["content"][:500]
            artifact["fallback_source"] = "latest_episodic_memory"

    return artifact


def format_handoff_markdown(artifact: Dict[str, Any]) -> str:
    """Renders a handoff artifact as agent-ready markdown."""
    to_client = artifact.get("to_client") or "any"
    lines = [
        "# Battery Handoff",
        "",
        f"**From:** {artifact.get('from_client', 'unknown')} → **To:** {to_client}",
        f"**Project:** `{artifact.get('project_root', '')}`",
        f"**Profile:** {artifact.get('profile', 'default')}",
        f"**Exported:** {artifact.get('created_at', '')}",
        f"**Verification:** {artifact.get('verification_status', 'unknown')}",
        "",
    ]

    if artifact.get("task_summary"):
        lines.extend(["## Task", "", artifact["task_summary"], ""])
    if artifact.get("next_action"):
        lines.extend(["## Next action", "", artifact["next_action"], ""])

    for heading, key in (
        ("Decisions", "decisions"),
        ("Rejected approaches", "rejected_approaches"),
        ("Blockers", "blockers"),
    ):
        values = artifact.get(key) or []
        if values:
            lines.append(f"## {heading}")
            lines.append("")
            lines.extend(f"- {value}" for value in values)
            lines.append("")

    changed = artifact.get("changed_files") or []
    if changed:
        lines.extend(["## Changed files", ""])
        lines.extend(f"- `{path}`" for path in changed[:30])
        lines.append("")

    context_items = artifact.get("active_context") or []
    if context_items:
        lines.extend(["## Active project context", ""])
        for item in context_items:
            lines.append(f"- **[{item['category']}]** {item['content']}")
        lines.append("")

    lineage = artifact.get("lineage") or []
    if lineage:
        lines.extend(["## Handoff lineage", ""])
        for hop in lineage[-5:]:
            lines.append(
                f"- `{hop.get('handoff_id', '?')[:8]}` "
                f"{hop.get('from_client', '?')} → {hop.get('to_client') or 'any'} "
                f"({hop.get('created_at', '')[:19]})"
            )
        lines.append("")

    lines.append(
        "_Resume this task using the task summary, next action, and decisions above. "
        "Verify changed files before editing._"
    )
    return "\n".join(lines)


def export_handoff(
    conn: sqlite3.Connection,
    *,
    project_root: Optional[Path] = None,
    profile: str = "default",
    from_client: str = "unknown",
    to_client: Optional[str] = None,
    stdout: bool = False,
) -> Dict[str, Any]:
    """Exports a handoff artifact to `.battery/handoff/` or stdout."""
    root = Path(project_root or Path.cwd()).resolve()
    artifact = build_handoff_artifact(
        conn,
        project_root=root,
        profile=profile,
        from_client=from_client,
        to_client=to_client,
    )
    markdown = format_handoff_markdown(artifact)

    if not artifact.get("checkpoint_id") and not artifact.get("task_summary"):
        raise ValueError(
            "No checkpoint or episodic memory found for this project. "
            "Run a session with hooks enabled or save a memory first."
        )

    result = {
        "handoff_id": artifact["handoff_id"],
        "path": None,
        "markdown_path": None,
        "artifact": artifact,
        "markdown": markdown,
    }

    if stdout:
        return result

    handoff_dir = get_handoff_dir(root)
    handoff_dir.mkdir(parents=True, exist_ok=True)
    json_path = handoff_dir / HANDOFF_JSON
    md_path = handoff_dir / HANDOFF_MD
    json_path.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
    md_path.write_text(markdown, encoding="utf-8")

    lineage_path = handoff_dir / LINEAGE_FILE
    with lineage_path.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "handoff_id": artifact["handoff_id"],
                    "from_client": from_client,
                    "to_client": to_client,
                    "created_at": artifact["created_at"],
                }
            )
            + "\n"
        )

    log_memory_event(
        conn,
        "HANDOFF_EXPORT",
        None,
        {
            "handoff_id": artifact["handoff_id"],
            "from_client": from_client,
            "to_client": to_client,
            "checkpoint_id": artifact.get("checkpoint_id"),
        },
    )

    result["path"] = str(json_path)
    result["markdown_path"] = str(md_path)
    return result


def read_handoff_artifact(
    *,
    project_root: Optional[Path] = None,
    file_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Reads a handoff artifact from disk."""
    if file_path is not None:
        path = Path(file_path)
    else:
        path = get_handoff_dir(project_root) / HANDOFF_JSON

    if not path.is_file():
        raise FileNotFoundError(f"No handoff artifact found at {path}")

    artifact = json.loads(path.read_text(encoding="utf-8"))
    artifact["_source_path"] = str(path)
    return artifact


def load_handoff(
    conn: sqlite3.Connection,
    md_path: Path,
    *,
    project_root: Optional[Path] = None,
    file_path: Optional[Path] = None,
    ingest: bool = False,
    to_client: Optional[str] = None,
) -> Dict[str, Any]:
    """Loads a handoff artifact and optionally ingests it as episodic memory."""
    artifact = read_handoff_artifact(project_root=project_root, file_path=file_path)
    if to_client:
        artifact["loaded_by"] = to_client

    markdown = format_handoff_markdown(artifact)
    result: Dict[str, Any] = {
        "handoff_id": artifact.get("handoff_id"),
        "from_client": artifact.get("from_client"),
        "verification_status": artifact.get("verification_status"),
        "markdown": markdown,
        "artifact": artifact,
        "memory_id": None,
    }

    if ingest:
        content = _handoff_ingest_content(artifact)
        vec = embed_text(content)
        memory_result = insert_memory(
            conn,
            content,
            vec,
            category="episodic",
            importance=0.9,
            source="handoff",
        )
        try:
            export_battery_md(conn, md_path)
        except OSError:
            pass
        log_memory_event(
            conn,
            "HANDOFF_LOAD",
            memory_result["id"],
            {
                "handoff_id": artifact.get("handoff_id"),
                "from_client": artifact.get("from_client"),
                "to_client": to_client,
            },
        )
        result["memory_id"] = memory_result["id"]
        result["memory_status"] = memory_result["status"]

    return result


def _handoff_ingest_content(artifact: Dict[str, Any]) -> str:
    """Formats handoff content for episodic memory storage."""
    prefix = (
        f"Handoff loaded from {artifact.get('from_client', 'unknown')} "
        f"(id={artifact.get('handoff_id', 'unknown')[:8]})."
    )
    body = _checkpoint_content(
        {
            "task_summary": artifact.get("task_summary"),
            "next_step": artifact.get("next_action"),
            "decisions": artifact.get("decisions"),
            "rejected_approaches": artifact.get("rejected_approaches"),
            "blockers": artifact.get("blockers"),
            "changed_files": artifact.get("changed_files"),
            "event_type": "handoff_load",
            "project_root": artifact.get("project_root"),
        }
    )
    return f"{prefix}\n{body}"


def get_latest_handoff_context(project_root: Optional[Path] = None) -> Optional[str]:
    """Returns markdown context from the latest on-disk handoff, if present."""
    handoff_dir = get_handoff_dir(project_root)
    md_path = handoff_dir / HANDOFF_MD
    json_path = handoff_dir / HANDOFF_JSON
    if not md_path.is_file() or not json_path.is_file():
        return None
    try:
        json.loads(json_path.read_text(encoding="utf-8"))
        return md_path.read_text(encoding="utf-8")
    except (OSError, json.JSONDecodeError):
        return None
