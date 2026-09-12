"""Battery Context Engine — Cross-Tool Handoff Scenario Benchmark.

Validates Cursor ↔ Claude (and multi-hop) handoff export/load and session-start
injection (O1-KR1.3).
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from battery.checkpoint import handle_hook_event, ingest_checkpoint
from battery.db import get_connection, init_db
from battery.handoff import (
    LINEAGE_FILE,
    export_handoff,
    get_handoff_dir,
    get_latest_handoff_context,
    load_handoff,
    verify_changed_files,
)
from battery.retrieval import hybrid_search

console = Console()

REPORT_PATH = Path(__file__).parent / "handoff_benchmark_report.md"
LINEAGE_HOPS_TARGET = 3


@dataclass
class HandoffScenarioResult:
    scenario_id: str
    description: str
    passed: bool
    detail: str


def _base_payload(workspace: Path, **overrides: Any) -> Dict[str, Any]:
    payload = {
        "session_id": "eval-session",
        "event_type": "session_end",
        "project_root": str(workspace),
        "task_summary": "Refactor auth middleware for JWT validation",
        "next_step": "Add integration tests in tests/test_auth.py",
        "decisions": [
            "Use RS256 not HS256 for service tokens",
            "Reject tokens without exp claim",
        ],
        "rejected_approaches": ["Session cookies for API routes"],
        "changed_files": [],
        "blockers": ["Waiting on staging deploy"],
    }
    payload.update(overrides)
    return payload


def _seed_checkpoint(conn, workspace: Path, payload: Dict[str, Any]) -> None:
    ingest_checkpoint(conn, payload, workspace / "BATTERY.md")
    conn.commit()


def _resume_tokens(payload: Dict[str, Any]) -> List[str]:
    """Tokens a new agent must see to resume without re-explanation."""
    tokens = [
        payload["task_summary"],
        payload["next_step"],
        payload["decisions"][0],
        payload["rejected_approaches"][0],
    ]
    return tokens


def _scenario_cursor_to_claude_resume(conn, workspace: Path) -> HandoffScenarioResult:
    """Simulated Cursor → Claude Code switch preserves mid-task context."""
    payload = _base_payload(workspace)
    _seed_checkpoint(conn, workspace, payload)

    export_result = export_handoff(
        conn,
        project_root=workspace,
        profile="default",
        from_client="cursor",
        to_client="claude-code",
    )
    conn.commit()

    load_result = load_handoff(
        conn,
        workspace / "BATTERY.md",
        project_root=workspace,
        ingest=False,
        to_client="claude-code",
    )
    markdown = load_result["markdown"]
    missing = [token for token in _resume_tokens(payload) if token not in markdown]
    passed = (
        export_result["artifact"]["to_client"] == "claude-code"
        and export_result["artifact"]["from_client"] == "cursor"
        and not missing
    )
    return HandoffScenarioResult(
        scenario_id="cursor-to-claude-resume",
        description="Export from Cursor and load in Claude preserves task/decisions/next step",
        passed=passed,
        detail=f"missing_tokens={len(missing)}",
    )


def _scenario_ingest_recall_after_switch(conn, workspace: Path) -> HandoffScenarioResult:
    """Ingested handoff is searchable after tool switch."""
    payload = _base_payload(
        workspace,
        task_summary="Migrate payment webhooks to idempotent handlers",
        decisions=["Store webhook dedupe keys in Redis"],
    )
    _seed_checkpoint(conn, workspace, payload)
    export_handoff(
        conn,
        project_root=workspace,
        from_client="cursor",
        to_client="claude-code",
    )
    conn.commit()

    load_handoff(
        conn,
        workspace / "BATTERY.md",
        project_root=workspace,
        ingest=True,
        to_client="claude-code",
    )
    conn.commit()

    results = hybrid_search(conn, "webhook dedupe Redis idempotent", limit=5, verify=False)
    found = any(
        "webhook" in r["content"].lower() and "redis" in r["content"].lower() for r in results
    )
    return HandoffScenarioResult(
        scenario_id="ingest-recall-after-switch",
        description="Handoff ingested as episodic memory is findable via hybrid search",
        passed=found,
        detail=f"results={len(results)}",
    )


def _scenario_lineage_three_hops(conn, workspace: Path) -> HandoffScenarioResult:
    """Three sequential exports produce traceable handoff lineage."""
    hops = [
        ("cursor", "claude-code", "Hop one: scaffold API"),
        ("claude-code", "cursor", "Hop two: add tests"),
        ("cursor", "gemini-cli", "Hop three: docs pass"),
    ]
    last_export = None
    for from_client, to_client, summary in hops:
        _seed_checkpoint(
            conn,
            workspace,
            _base_payload(workspace, task_summary=summary, next_step=f"Continue {summary}"),
        )
        last_export = export_handoff(
            conn,
            project_root=workspace,
            profile="default",
            from_client=from_client,
            to_client=to_client,
        )
        conn.commit()

    lineage = last_export["artifact"]["lineage"]
    lineage_path = get_handoff_dir(workspace) / LINEAGE_FILE
    file_hops = 0
    if lineage_path.is_file():
        file_hops = sum(
            1 for line in lineage_path.read_text(encoding="utf-8").splitlines() if line.strip()
        )

    passed = len(lineage) >= 2 and file_hops >= LINEAGE_HOPS_TARGET
    return HandoffScenarioResult(
        scenario_id="lineage-three-hops",
        description="Three export hops append lineage in artifact and lineage.jsonl",
        passed=passed,
        detail=f"artifact_lineage={len(lineage)}, file_hops={file_hops}",
    )


def _scenario_session_start_injection(conn, workspace: Path) -> HandoffScenarioResult:
    """SessionStart hook injects latest handoff markdown for the receiving client."""
    payload = _base_payload(
        workspace,
        task_summary="Wire OAuth callback handler in auth/routes.py",
    )
    _seed_checkpoint(conn, workspace, payload)
    export_handoff(
        conn,
        project_root=workspace,
        from_client="cursor",
        to_client="claude-code",
    )
    conn.commit()

    result = handle_hook_event(
        conn,
        {"hook_event_name": "SessionStart", "cwd": str(workspace)},
        workspace / "BATTERY.md",
    )
    context = result.get("additionalContext") or ""
    passed = (
        result["status"] == "ok"
        and "Battery handoff (switch tools)" in context
        and "OAuth callback handler" in context
    )
    return HandoffScenarioResult(
        scenario_id="session-start-injection",
        description="SessionStart returns handoff markdown when artifact exists",
        passed=passed,
        detail=f"context_len={len(context)}",
    )


def _scenario_file_verification_on_export(conn, workspace: Path) -> HandoffScenarioResult:
    """Changed-files verification status is computed on export."""
    src = workspace / "src" / "api.py"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text("def api(): pass\n", encoding="utf-8")

    payload = _base_payload(
        workspace,
        changed_files=[str(src.relative_to(workspace)), "missing/file.py"],
    )
    _seed_checkpoint(conn, workspace, payload)
    export_result = export_handoff(
        conn,
        project_root=workspace,
        from_client="cursor",
        to_client="claude-code",
    )
    conn.commit()

    artifact = export_result["artifact"]
    passed = (
        artifact["verification_status"] == "partial"
        and artifact["verification"]["valid_count"] == 1
        and artifact["verification"]["missing_count"] == 1
    )
    verify = verify_changed_files(payload["changed_files"], workspace)
    passed = passed and verify["status"] == "partial"
    return HandoffScenarioResult(
        scenario_id="file-verification-on-export",
        description="Export marks handoff verification partial when cited files are missing",
        passed=passed,
        detail=f"status={artifact['verification_status']}",
    )


def _scenario_latest_context_reader(conn, workspace: Path) -> HandoffScenarioResult:
    """get_latest_handoff_context returns agent-ready markdown from disk."""
    payload = _base_payload(workspace, next_step="Run battery eval --handoff")
    _seed_checkpoint(conn, workspace, payload)
    export_handoff(conn, project_root=workspace, from_client="cursor")
    conn.commit()

    context = get_latest_handoff_context(workspace)
    passed = context is not None and "Run battery eval --handoff" in context
    return HandoffScenarioResult(
        scenario_id="latest-context-reader",
        description="Latest handoff markdown readable from .battery/handoff/",
        passed=passed,
        detail=f"present={context is not None}",
    )


HandoffScenarioFn = Callable[[Any, Path], HandoffScenarioResult]

HANDOFF_SCENARIOS: List[tuple[str, HandoffScenarioFn]] = [
    ("cursor-to-claude-resume", _scenario_cursor_to_claude_resume),
    ("ingest-recall-after-switch", _scenario_ingest_recall_after_switch),
    ("lineage-three-hops", _scenario_lineage_three_hops),
    ("session-start-injection", _scenario_session_start_injection),
    ("file-verification-on-export", _scenario_file_verification_on_export),
    ("latest-context-reader", _scenario_latest_context_reader),
]


def run_handoff_benchmark(output_markdown: bool = True) -> Dict[str, Any]:
    """Runs all cross-tool handoff scenarios in isolated workspaces."""
    console.print(
        Panel.fit(
            "[bold cyan]🔋 Battery Cross-Tool Handoff Benchmark[/bold cyan]\n"
            f"Scenarios: [bold]{len(HANDOFF_SCENARIOS)}[/bold] polyglot continuity cases\n"
            f"Target:    [bold]all scenarios pass[/bold], lineage ≥ {LINEAGE_HOPS_TARGET} hops",
            title="Handoff Benchmark Configuration",
        )
    )

    import shutil

    base_workspace = Path(__file__).parent / "temp_handoff_workspace"
    if base_workspace.exists():
        shutil.rmtree(base_workspace, ignore_errors=True)
    base_workspace.mkdir(parents=True, exist_ok=True)

    results: List[HandoffScenarioResult] = []
    for scenario_id, fn in HANDOFF_SCENARIOS:
        workspace = base_workspace / scenario_id
        workspace.mkdir(parents=True, exist_ok=True)
        conn = get_connection(Path(":memory:"))
        init_db(conn)
        try:
            results.append(fn(conn, workspace))
        finally:
            conn.close()

    shutil.rmtree(base_workspace, ignore_errors=True)

    passed = sum(1 for r in results if r.passed)
    summary: Dict[str, Any] = {
        "total_scenarios": len(results),
        "passed_scenarios": passed,
        "lineage_hops_target": LINEAGE_HOPS_TARGET,
        "all_passed": passed == len(results),
        "scenarios": [
            {
                "id": r.scenario_id,
                "description": r.description,
                "passed": r.passed,
                "detail": r.detail,
            }
            for r in results
        ],
    }

    table = Table(title="🔀 Cross-Tool Handoff Benchmark Results", header_style="bold magenta")
    table.add_column("Scenario", style="cyan", width=30)
    table.add_column("Pass", justify="center")
    table.add_column("Detail", style="dim")

    for r in results:
        table.add_row(
            r.scenario_id,
            "[green]✓[/green]" if r.passed else "[red]✗[/red]",
            r.detail,
        )

    console.print(table)
    console.print(
        f"\n[bold]Summary:[/bold] {passed}/{len(results)} scenarios passed "
        f"(target: all pass, lineage ≥ {LINEAGE_HOPS_TARGET} hops)"
    )

    if output_markdown:
        _write_report(summary)
        console.print(f"\nReport saved to [cyan]{REPORT_PATH}[/cyan]")

    return summary


def _write_report(summary: Dict[str, Any]) -> None:
    rows = "\n".join(
        f"| **{s['id']}** | {'PASS' if s['passed'] else 'FAIL'} | {s['detail']} |"
        for s in summary["scenarios"]
    )
    md = f"""# 🔋 Battery — Cross-Tool Handoff Benchmark Report

**Scenarios:** {summary["total_scenarios"]} polyglot continuity cases\
**Target:** all pass; lineage ≥ {summary["lineage_hops_target"]} hops traceable

---

## Summary

| Metric | Result | Target | Status |
| :--- | :---: | :---: | :---: |
| **Scenarios passed** | **{summary["passed_scenarios"]}/{summary["total_scenarios"]}** | all | {"✅" if summary["all_passed"] else "❌"} |

---

## Scenario Results

| Scenario | Pass | Detail |
| :--- | :---: | :--- |
{rows}
"""
    REPORT_PATH.write_text(md, encoding="utf-8")
