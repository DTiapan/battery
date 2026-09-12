"""Claude Code hook installation and settings merge."""

import json
import stat
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

BATTERY_HOOK_MARKER = "battery-context-engine"
HOOK_SCRIPT_NAME = "battery-hook.sh"

HOOK_EVENTS = {
    "SessionEnd": [{"matcher": "", "timeout": 15}],
    "PreCompact": [
        {"matcher": "auto", "timeout": 15},
        {"matcher": "manual", "timeout": 15},
    ],
}


def _hook_command(project: bool) -> str:
    if project:
        return "$CLAUDE_PROJECT_DIR/.claude/hooks/battery-hook.sh"
    return "battery hook run"


def hook_shell_script(project: bool = True) -> str:
    """Returns the shell script invoked by Claude Code hooks."""
    if project:
        inner = "battery hook run"
    else:
        inner = "battery hook run"
    return f"""#!/usr/bin/env bash
# {BATTERY_HOOK_MARKER}
set -euo pipefail
{inner}
"""


def _settings_path(scope: Literal["user", "project"], project_dir: Optional[Path] = None) -> Path:
    if scope == "user":
        return Path.home() / ".claude" / "settings.json"
    root = project_dir or Path.cwd()
    return root / ".claude" / "settings.json"


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def _is_battery_hook(entry: Dict[str, Any]) -> bool:
    command = str(entry.get("command", ""))
    return (
        BATTERY_HOOK_MARKER in command
        or "battery hook run" in command
        or "battery-hook.sh" in command
    )


def _build_hook_entries(project: bool) -> List[Dict[str, Any]]:
    command = _hook_command(project)
    entries: List[Dict[str, Any]] = []
    for event_name, matchers in HOOK_EVENTS.items():
        for spec in matchers:
            hook_def: Dict[str, Any] = {
                "type": "command",
                "command": command,
                "timeout": spec.get("timeout", 15),
            }
            matcher = spec.get("matcher", "")
            group: Dict[str, Any] = {"hooks": [hook_def]}
            if matcher:
                group["matcher"] = matcher
            entries.append({"event": event_name, "group": group})
    return entries


def merge_battery_hooks(settings: Dict[str, Any], project: bool) -> Dict[str, Any]:
    """Merges Battery hook groups into Claude settings without removing other hooks."""
    hooks = settings.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        hooks = {}
        settings["hooks"] = hooks

    for entry in _build_hook_entries(project):
        event_name = entry["event"]
        group = entry["group"]
        existing_groups = hooks.setdefault(event_name, [])
        if not isinstance(existing_groups, list):
            existing_groups = []
            hooks[event_name] = existing_groups

        filtered = [
            g
            for g in existing_groups
            if not any(_is_battery_hook(h) for h in g.get("hooks", []) if isinstance(h, dict))
        ]
        filtered.append(group)
        hooks[event_name] = filtered

    return settings


def strip_battery_hooks(settings: Dict[str, Any]) -> Dict[str, Any]:
    """Removes Battery hook entries from Claude settings."""
    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        return settings

    for event_name, groups in list(hooks.items()):
        if not isinstance(groups, list):
            continue
        kept = []
        for group in groups:
            if not isinstance(group, dict):
                kept.append(group)
                continue
            inner = [
                h for h in group.get("hooks", []) if isinstance(h, dict) and not _is_battery_hook(h)
            ]
            if inner:
                new_group = dict(group)
                new_group["hooks"] = inner
                kept.append(new_group)
        if kept:
            hooks[event_name] = kept
        else:
            del hooks[event_name]
    return settings


def install_hooks(
    scope: Literal["user", "project"] = "project",
    project_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Installs Battery hooks into Claude Code settings."""
    project = scope == "project"
    root = project_dir or Path.cwd()

    if project:
        hook_dir = root / ".claude" / "hooks"
        hook_dir.mkdir(parents=True, exist_ok=True)
        script_path = hook_dir / HOOK_SCRIPT_NAME
        script_path.write_text(hook_shell_script(project=True), encoding="utf-8")
        script_path.chmod(script_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    settings_path = _settings_path(scope, root if project else None)
    settings = _read_json(settings_path)
    merge_battery_hooks(settings, project=project)
    _write_json(settings_path, settings)

    return {
        "scope": scope,
        "settings_path": str(settings_path),
        "hook_script": str((root / ".claude" / "hooks" / HOOK_SCRIPT_NAME)) if project else None,
        "events": list(HOOK_EVENTS.keys()),
    }


def uninstall_hooks(
    scope: Literal["user", "project"] = "project",
    project_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Removes Battery hooks from Claude Code settings."""
    project = scope == "project"
    root = project_dir or Path.cwd()
    settings_path = _settings_path(scope, root if project else None)
    settings = _read_json(settings_path)
    strip_battery_hooks(settings)
    _write_json(settings_path, settings)

    removed_script = None
    if project:
        script_path = root / ".claude" / "hooks" / HOOK_SCRIPT_NAME
        if script_path.exists():
            script_path.unlink()
            removed_script = str(script_path)

    return {"scope": scope, "settings_path": str(settings_path), "removed_script": removed_script}


def hooks_installed(
    scope: Literal["user", "project"] = "project", project_dir: Optional[Path] = None
) -> bool:
    """Returns True if Battery hooks appear in Claude settings."""
    root = project_dir or Path.cwd()
    settings = _read_json(_settings_path(scope, root if scope == "project" else None))
    hooks = settings.get("hooks", {})
    if not isinstance(hooks, dict):
        return False
    for groups in hooks.values():
        if not isinstance(groups, list):
            continue
        for group in groups:
            if isinstance(group, dict):
                for hook in group.get("hooks", []):
                    if isinstance(hook, dict) and _is_battery_hook(hook):
                        return True
    return False
