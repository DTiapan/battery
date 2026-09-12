"""Install and manage git post-commit hooks for Battery."""

from __future__ import annotations

import stat
from pathlib import Path
from typing import Any, Dict, Optional

from battery.git_capture import BATTERY_GIT_MARKER

HOOK_SCRIPT_LINES = (
    "#!/bin/sh",
    f"# {BATTERY_GIT_MARKER}",
    "battery git capture 2>/dev/null || true",
)


def post_commit_hook_path(project_root: Path) -> Path:
    return project_root.resolve() / ".git" / "hooks" / "post-commit"


def git_hook_installed(project_root: Optional[Path] = None) -> bool:
    """Returns True if Battery post-commit hook is installed."""
    root = (project_root or Path.cwd()).resolve()
    hook_path = post_commit_hook_path(root)
    if not hook_path.is_file():
        return False
    try:
        content = hook_path.read_text(encoding="utf-8")
    except OSError:
        return False
    return BATTERY_GIT_MARKER in content


def _render_hook(existing: str) -> str:
    block = "\n".join(HOOK_SCRIPT_LINES)
    if BATTERY_GIT_MARKER in existing:
        return existing
    stripped = existing.rstrip()
    if stripped:
        return f"{stripped}\n\n{block}\n"
    return f"{block}\n"


def install_git_hook(project_root: Optional[Path] = None) -> Dict[str, Any]:
    """Installs Battery post-commit hook in the project git repo."""
    root = (project_root or Path.cwd()).resolve()
    git_dir = root / ".git"
    if not git_dir.is_dir():
        raise ValueError(f"Not a git repository: {root}")

    hook_path = post_commit_hook_path(root)
    hook_path.parent.mkdir(parents=True, exist_ok=True)

    existing = hook_path.read_text(encoding="utf-8") if hook_path.exists() else ""
    hook_path.write_text(_render_hook(existing), encoding="utf-8")
    hook_path.chmod(hook_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    return {
        "hook_path": str(hook_path),
        "project_root": str(root),
        "already_installed": BATTERY_GIT_MARKER in existing,
    }


def uninstall_git_hook(project_root: Optional[Path] = None) -> Dict[str, Any]:
    """Removes Battery lines from the post-commit hook."""
    root = (project_root or Path.cwd()).resolve()
    hook_path = post_commit_hook_path(root)
    if not hook_path.is_file():
        return {"hook_path": str(hook_path), "removed": False}

    lines = hook_path.read_text(encoding="utf-8").splitlines()
    kept: list[str] = []
    skip_next_blank = False
    for line in lines:
        if BATTERY_GIT_MARKER in line:
            skip_next_blank = True
            continue
        if "battery git capture" in line:
            skip_next_blank = True
            continue
        if skip_next_blank and not line.strip():
            skip_next_blank = False
            continue
        skip_next_blank = False
        kept.append(line)

    if not kept or all(not line.strip() or line.startswith("#") for line in kept):
        hook_path.unlink(missing_ok=True)
        removed = True
    else:
        content = "\n".join(kept).rstrip() + "\n"
        hook_path.write_text(content, encoding="utf-8")
        removed = True

    return {"hook_path": str(hook_path), "removed": removed}
