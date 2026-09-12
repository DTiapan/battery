"""Health checks and adoption diagnostics for Battery."""

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import pysqlite3 as sqlite3
except ImportError:
    import sqlite3

from battery.config import EMBEDDING_DIM, get_profile_db_path
from battery.git_hooks import git_hook_installed
from battery.hooks import hooks_installed
from battery.mcp_server import format_context_resource, format_rules_resource
from battery.migrate import SCHEMA_VERSION, get_schema_version, migrate_db
from battery.retrieval import hybrid_search
from battery.sync import export_battery_md

ONBOARD_SEED_MEMORIES: List[tuple[str, str]] = [
    (
        "Battery stores project rules and architectural decisions locally using "
        "hybrid BM25 + vector search with a git-committable BATTERY.md mirror.",
        "decision",
    ),
    (
        "Prefer explicit LIMIT clauses on all production SQL queries.",
        "rule",
    ),
]


def _check(name: str, ok: bool, detail: str, fix: Optional[str] = None) -> Dict[str, Any]:
    return {"name": name, "ok": ok, "detail": detail, "fix": fix}


def _md_hash(path: Path) -> str:
    if not path.exists():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_doctor(
    conn: sqlite3.Connection,
    md_path: Path,
    *,
    adoption: bool = False,
    project_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Runs Battery health and optional adoption checks."""
    checks: List[Dict[str, Any]] = []

    migrate_db(conn)
    version = get_schema_version(conn)
    checks.append(
        _check(
            "schema_version",
            version >= SCHEMA_VERSION,
            f"schema v{version} (target v{SCHEMA_VERSION})",
            None if version >= SCHEMA_VERSION else "Run any battery command to migrate",
        )
    )

    try:
        conn.execute("SELECT vec_version()")
        vec_ok = True
        vec_detail = "sqlite-vec loaded"
    except sqlite3.OperationalError as exc:
        vec_ok = False
        vec_detail = str(exc)

    checks.append(
        _check("sqlite_vec", vec_ok, vec_detail, "Reinstall battery with sqlean-py / pysqlite3")
    )

    row = conn.execute("SELECT COUNT(*) FROM memories WHERE is_deleted = 0").fetchone()
    memory_count = row[0] if row else 0
    checks.append(_check("memories", True, f"{memory_count} active memories", None))

    # Mirror sync drift check
    drift = False
    drift_detail = "BATTERY.md in sync"
    if md_path.exists():
        temp = md_path.with_suffix(".md.doctor.tmp")
        export_battery_md(conn, temp)
        if _md_hash(temp) != _md_hash(md_path):
            drift = True
            drift_detail = "BATTERY.md differs from database export"
        temp.unlink(missing_ok=True)
    checks.append(
        _check(
            "mirror_sync",
            not drift,
            drift_detail,
            "Run: battery sync --import" if drift else None,
        )
    )

    if adoption:
        root = project_dir or Path.cwd()
        claude_user = Path.home() / "Library/Application Support/Claude/claude_desktop_config.json"
        if not claude_user.exists():
            claude_user = Path.home() / ".config/Claude/claude_desktop_config.json"

        mcp_ok = False
        mcp_detail = "MCP config not found"
        for cfg_path in (
            claude_user,
            root / ".cursor/mcp.json",
            Path.home() / ".cursor/mcp.json",
        ):
            if not cfg_path.exists():
                continue
            try:
                data = json.loads(cfg_path.read_text(encoding="utf-8"))
                servers = data.get("mcpServers") or data.get("mcp_servers") or {}
                if any("battery" in k.lower() for k in servers):
                    mcp_ok = True
                    mcp_detail = f"Battery MCP found in {cfg_path}"
                    break
            except (json.JSONDecodeError, OSError):
                continue

        checks.append(
            _check(
                "mcp_config",
                mcp_ok,
                mcp_detail,
                "Run: battery setup --client all",
            )
        )

        hook_ok = hooks_installed("project", root) or hooks_installed("user", root)
        checks.append(
            _check(
                "claude_hooks",
                hook_ok,
                "Battery hooks installed" if hook_ok else "Claude Code hooks not installed",
                "Run: battery hook install --scope project",
            )
        )

        git_ok = git_hook_installed(root)
        checks.append(
            _check(
                "git_post_commit",
                git_ok,
                "Git post-commit hook installed"
                if git_ok
                else "Git post-commit hook not installed",
                "Run: battery git install",
            )
        )

        ctx = format_context_resource(conn)
        ctx_ok = memory_count > 0 and "No active" not in ctx and len(ctx.strip()) > 120
        checks.append(
            _check(
                "mcp_context",
                ctx_ok,
                "battery://context returns project context"
                if ctx_ok
                else "battery://context empty or placeholder",
                "Run: battery onboard --seed or battery add ...",
            )
        )

        rules = format_rules_resource(conn)
        rules_ok = memory_count > 0 and "No active rules found" not in rules
        checks.append(
            _check(
                "mcp_rules",
                rules_ok,
                "battery://rules returns active rules"
                if rules_ok
                else "battery://rules has no rule entries",
                "Run: battery add ... -c rule",
            )
        )

        if memory_count > 0:
            sample = conn.execute(
                "SELECT content FROM memories WHERE is_deleted = 0 ORDER BY id LIMIT 1"
            ).fetchone()
            sample_text = sample[0] if sample else ""
            words = sample_text.split()[:4]
            query = " ".join(words) if len(words) >= 2 else sample_text[:48]
            results = hybrid_search(conn, query, limit=3, verify=False)
            recall_ok = len(results) > 0
            checks.append(
                _check(
                    "recall_smoke",
                    recall_ok,
                    f"hybrid recall returned {len(results)} hit(s) for seeded query",
                    'Run: battery query "<topic>" to debug retrieval',
                )
            )
        else:
            checks.append(
                _check(
                    "recall_smoke",
                    False,
                    "No memories to test recall",
                    "Run: battery onboard --seed",
                )
            )

    passed = sum(1 for c in checks if c["ok"])
    return {
        "checks": checks,
        "passed": passed,
        "total": len(checks),
        "healthy": passed == len(checks),
        "embedding_dim": EMBEDDING_DIM,
        "db_path": str(get_profile_db_path()),
        "md_path": str(md_path),
    }
