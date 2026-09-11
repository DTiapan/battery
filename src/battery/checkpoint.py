"""Session checkpoint ingestion from Claude Code lifecycle hooks."""

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import pysqlite3 as sqlite3
except ImportError:
    import sqlite3

from battery.db import insert_memory, insert_session_checkpoint
from battery.embeddings import embed_text
from battery.sync import export_battery_md


def _checkpoint_content(payload: Dict[str, Any]) -> str:
    """Formats checkpoint payload as searchable episodic memory text."""
    lines: List[str] = []
    if payload.get("task_summary"):
        lines.append(f"Task: {payload['task_summary']}")
    if payload.get("next_step"):
        lines.append(f"Next step: {payload['next_step']}")
    for decision in payload.get("decisions") or []:
        lines.append(f"Decision: {decision}")
    for rejected in payload.get("rejected_approaches") or []:
        lines.append(f"Rejected: {rejected}")
    for blocker in payload.get("blockers") or []:
        lines.append(f"Blocker: {blocker}")
    changed = payload.get("changed_files") or []
    if changed:
        lines.append("Changed files: " + ", ".join(str(f) for f in changed[:20]))
    if not lines:
        lines.append(
            f"Session checkpoint ({payload.get('event_type', 'unknown')}) "
            f"for project {payload.get('project_root', 'unknown')}"
        )
    return "\n".join(lines)


def build_checkpoint_payload(
    hook_input: Dict[str, Any],
    *,
    event_type: str,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Builds a structured checkpoint from Claude hook stdin JSON."""
    project_root = hook_input.get("cwd") or hook_input.get("project_root") or str(Path.cwd())
    payload: Dict[str, Any] = {
        "session_id": hook_input.get("session_id", "unknown"),
        "event_type": event_type,
        "project_root": project_root,
        "hook_event_name": hook_input.get("hook_event_name"),
        "transcript_path": hook_input.get("transcript_path"),
        "task_summary": os.environ.get("BATTERY_CHECKPOINT_SUMMARY", "").strip(),
        "decisions": [],
        "rejected_approaches": [],
        "changed_files": [],
        "blockers": [],
        "next_step": "",
    }
    if extra:
        payload.update(extra)
    return payload


def ingest_checkpoint(
    conn: sqlite3.Connection,
    payload: Dict[str, Any],
    md_path: Path,
) -> Dict[str, Any]:
    """Persists checkpoint to session_checkpoints and episodic memory."""
    content = _checkpoint_content(payload)
    vec = embed_text(content)
    citations = [{"file_path": f} for f in (payload.get("changed_files") or [])[:10] if f]

    memory_result = insert_memory(
        conn,
        content,
        vec,
        category="episodic",
        importance=0.8,
        source="hook",
        session_id=payload.get("session_id"),
        citations=citations or None,
    )

    checkpoint_id = insert_session_checkpoint(
        conn,
        session_id=str(payload.get("session_id", "unknown")),
        event_type=str(payload.get("event_type", "session_end")),
        payload=payload,
        project_root=payload.get("project_root"),
        memory_id=memory_result["id"],
    )

    try:
        export_battery_md(conn, md_path)
    except OSError:
        pass

    return {
        "checkpoint_id": checkpoint_id,
        "memory_id": memory_result["id"],
        "memory_status": memory_result["status"],
        "content_preview": content[:200],
    }


def handle_hook_event(
    conn: sqlite3.Connection,
    hook_input: Dict[str, Any],
    md_path: Path,
) -> Dict[str, Any]:
    """Dispatches a Claude hook event to the appropriate checkpoint handler."""
    event_name = hook_input.get("hook_event_name", "")

    if event_name == "SessionEnd":
        payload = build_checkpoint_payload(hook_input, event_type="session_end")
        result = ingest_checkpoint(conn, payload, md_path)
        return {"status": "ok", "event": event_name, **result}

    if event_name == "PreCompact":
        trigger = hook_input.get("trigger", "auto")
        payload = build_checkpoint_payload(hook_input, event_type="pre_compact", extra={"trigger": trigger})
        result = ingest_checkpoint(conn, payload, md_path)
        return {"status": "ok", "event": event_name, "trigger": trigger, **result}

    if event_name == "SessionStart":
        from battery.handoff import get_latest_handoff_context

        project_root = hook_input.get("cwd") or str(Path.cwd())
        handoff_context = get_latest_handoff_context(Path(project_root))
        if handoff_context:
            return {
                "status": "ok",
                "event": event_name,
                "additionalContext": f"Battery handoff (switch tools):\n{handoff_context[:4000]}",
            }

        checkpoints = _latest_checkpoint_for_project(conn, project_root)
        if checkpoints:
            preview = _checkpoint_content(checkpoints["payload"])[:500]
            return {
                "status": "ok",
                "event": event_name,
                "additionalContext": f"Battery latest checkpoint:\n{preview}",
            }
        return {"status": "ok", "event": event_name, "additionalContext": ""}

    return {"status": "ignored", "event": event_name}


def _latest_checkpoint_for_project(conn: sqlite3.Connection, project_root: str) -> Optional[Dict[str, Any]]:
    from battery.db import list_session_checkpoints

    rows = list_session_checkpoints(conn, project_root=project_root, limit=1)
    return rows[0] if rows else None


def parse_hook_stdin(raw: str) -> Dict[str, Any]:
    """Parses hook JSON from stdin."""
    if not raw.strip():
        return {}
    return json.loads(raw)
