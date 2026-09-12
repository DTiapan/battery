"""Battery Context Engine — Context Rot Benchmark Suite.

Validates JIT citation verification and prune behavior: stale or missing file
citations must never surface in verified recall (O2-KR2.1).
"""

import statistics
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from battery.db import get_connection, hash_file_snippet, init_db, insert_memory
from battery.embeddings import embed_text
from battery.prune import prune_stale_memories
from battery.retrieval import hybrid_search
from battery.verify import filter_verified_results, verify_memory

console = Console()

REPORT_PATH = Path(__file__).parent / "rot_benchmark_report.md"
VERIFY_P95_TARGET_MS = 10.0


@dataclass
class RotScenarioResult:
    scenario_id: str
    description: str
    passed: bool
    stale_recall_failure: bool
    verify_latency_ms: float
    detail: str


def _insert_cited_memory(
    conn,
    content: str,
    file_path: Path,
    *,
    category: str = "decision",
) -> int:
    vec = embed_text(content)
    snippet_hash = hash_file_snippet(file_path)
    result = insert_memory(
        conn,
        content,
        vec,
        category=category,
        citations=[{"file_path": str(file_path), "snippet_hash": snippet_hash}],
    )
    conn.commit()
    return result["id"]


def _insert_plain_memory(conn, content: str, *, category: str = "rule") -> int:
    vec = embed_text(content)
    result = insert_memory(conn, content, vec, category=category)
    conn.commit()
    return result["id"]


def _recall_verified(conn, query: str, limit: int = 5) -> tuple[List[Dict[str, Any]], float]:
    """Returns verified hybrid results and verify-phase latency in ms."""
    candidates = hybrid_search(conn, query, limit=limit, verify=False)
    t0 = time.perf_counter()
    verified = filter_verified_results(conn, candidates)
    verify_ms = (time.perf_counter() - t0) * 1000
    return verified, verify_ms


def _scenario_stale_snippet_excluded(conn, workspace: Path) -> RotScenarioResult:
    """Changed file content must not leak via cited memory."""
    config = workspace / "config.py"
    config.write_text("PORT = 5432\n", encoding="utf-8")
    memory_id = _insert_cited_memory(conn, "Production database listens on port 5432", config)

    config.write_text("PORT = 3306\n", encoding="utf-8")

    unverified = hybrid_search(conn, "port 5432", limit=5, verify=False)
    control_finds_stale = any(r["id"] == memory_id for r in unverified)
    assert verify_memory(conn, memory_id) == "stale"

    verified, verify_ms = _recall_verified(conn, "port 5432")
    stale_leaked = any(r["id"] == memory_id for r in verified)

    passed = not stale_leaked and control_finds_stale
    return RotScenarioResult(
        scenario_id="stale-snippet-excluded",
        description="Cited memory with changed file snippet is filtered on verified recall",
        passed=passed,
        stale_recall_failure=stale_leaked,
        verify_latency_ms=verify_ms,
        detail=f"control_unverified_includes_stale={control_finds_stale}",
    )


def _scenario_missing_file_excluded(conn, workspace: Path) -> RotScenarioResult:
    """Deleted cited file must not leak via verified recall."""
    api = workspace / "api.py"
    api.write_text("def handler(): return 200\n", encoding="utf-8")
    memory_id = _insert_cited_memory(conn, "HTTP handler lives in api.py", api)

    api.unlink()
    assert verify_memory(conn, memory_id) == "missing"

    verified, verify_ms = _recall_verified(conn, "HTTP handler api")
    stale_leaked = any(r["id"] == memory_id for r in verified)
    passed = not stale_leaked
    return RotScenarioResult(
        scenario_id="missing-file-excluded",
        description="Cited memory with deleted file is filtered on verified recall",
        passed=passed,
        stale_recall_failure=stale_leaked,
        verify_latency_ms=verify_ms,
        detail="file_deleted",
    )


def _scenario_valid_citation_recall(conn, workspace: Path) -> RotScenarioResult:
    """Unchanged citation should still recall."""
    schema = workspace / "schema.sql"
    schema.write_text("CREATE TABLE users (id INTEGER PRIMARY KEY);\n", encoding="utf-8")
    memory_id = _insert_cited_memory(conn, "Users table defined in schema.sql", schema)

    verified, verify_ms = _recall_verified(conn, "users table schema")
    found = any(r["id"] == memory_id for r in verified)
    return RotScenarioResult(
        scenario_id="valid-citation-recall",
        description="Valid cited memory is returned on verified recall",
        passed=found,
        stale_recall_failure=False,
        verify_latency_ms=verify_ms,
        detail=f"found={found}",
    )


def _scenario_uncited_memory_immune(conn, workspace: Path) -> RotScenarioResult:
    """Memories without citations are unaffected by unrelated file rot."""
    rot_file = workspace / "legacy.py"
    rot_file.write_text("old = True\n", encoding="utf-8")
    memory_id = _insert_plain_memory(conn, "Always run pytest with -q for CI speed")

    rot_file.unlink()
    verified, verify_ms = _recall_verified(conn, "pytest CI")
    found = any(r["id"] == memory_id for r in verified)
    return RotScenarioResult(
        scenario_id="uncited-memory-immune",
        description="Uncited memory recalls even when unrelated files are deleted",
        passed=found,
        stale_recall_failure=False,
        verify_latency_ms=verify_ms,
        detail=f"found={found}",
    )


def _scenario_stale_yields_fresh_fallback(conn, workspace: Path) -> RotScenarioResult:
    """When a cited memory goes stale, an uncited fresh memory should rank instead."""
    api = workspace / "service.py"
    api.write_text("PORT = 8080\n", encoding="utf-8")
    stale_id = _insert_cited_memory(conn, "Internal API service runs on port 8080", api)
    fresh_id = _insert_plain_memory(
        conn,
        "Internal API service now runs on port 9090 after migration",
        category="decision",
    )

    api.write_text("PORT = 9090\n", encoding="utf-8")
    assert verify_memory(conn, stale_id) == "stale"

    verified, verify_ms = _recall_verified(conn, "internal API port")
    stale_leaked = any(r["id"] == stale_id for r in verified)
    fresh_found = any(r["id"] == fresh_id for r in verified)
    passed = not stale_leaked and fresh_found
    return RotScenarioResult(
        scenario_id="stale-yields-fresh-fallback",
        description="Stale cited memory suppressed; fresh uncited memory still recalls",
        passed=passed,
        stale_recall_failure=stale_leaked,
        verify_latency_ms=verify_ms,
        detail=f"fresh_found={fresh_found}",
    )


def _scenario_prune_tombstones_stale(conn, workspace: Path) -> RotScenarioResult:
    """battery prune must tombstone stale cited memories."""
    env = workspace / "env.py"
    env.write_text("DEBUG = True\n", encoding="utf-8")
    memory_id = _insert_cited_memory(conn, "Debug mode enabled in env.py", env)

    env.write_text("DEBUG = False\n", encoding="utf-8")
    prune_result = prune_stale_memories(conn, project_root=workspace, dry_run=False)
    pruned = memory_id in prune_result["pruned_ids"]

    raw = hybrid_search(conn, "debug mode env", limit=5, verify=False)
    still_searchable = any(r["id"] == memory_id for r in raw)
    passed = pruned and not still_searchable
    return RotScenarioResult(
        scenario_id="prune-tombstones-stale",
        description="Prune tombstones stale cited memory so it no longer appears in search",
        passed=passed,
        stale_recall_failure=False,
        verify_latency_ms=0.0,
        detail=f"pruned={pruned}, still_searchable={still_searchable}",
    )


RotScenarioFn = Callable[[Any, Path], RotScenarioResult]

ROT_SCENARIOS: List[tuple[str, RotScenarioFn]] = [
    ("stale-snippet-excluded", _scenario_stale_snippet_excluded),
    ("missing-file-excluded", _scenario_missing_file_excluded),
    ("valid-citation-recall", _scenario_valid_citation_recall),
    ("uncited-memory-immune", _scenario_uncited_memory_immune),
    ("stale-yields-fresh-fallback", _scenario_stale_yields_fresh_fallback),
    ("prune-tombstones-stale", _scenario_prune_tombstones_stale),
]


def run_rot_benchmark(output_markdown: bool = True) -> Dict[str, Any]:
    """Runs all context-rot scenarios in an isolated temp workspace."""
    console.print(
        Panel.fit(
            "[bold cyan]🔋 Battery Context Rot Benchmark[/bold cyan]\n"
            f"Scenarios: [bold]{len(ROT_SCENARIOS)}[/bold] citation / prune rot cases\n"
            f"Target:    [bold]0 stale-recall failures[/bold], verify p95 < {VERIFY_P95_TARGET_MS}ms",
            title="Rot Benchmark Configuration",
        )
    )

    workspace = Path(__file__).parent / "temp_rot_workspace"

    def cleanup_workspace() -> None:
        import shutil

        if workspace.exists():
            shutil.rmtree(workspace, ignore_errors=True)

    cleanup_workspace()
    workspace.mkdir(parents=True, exist_ok=True)

    results: List[RotScenarioResult] = []
    for _name, fn in ROT_SCENARIOS:
        conn = get_connection(Path(":memory:"))
        init_db(conn)
        try:
            results.append(fn(conn, workspace))
        finally:
            conn.close()

    cleanup_workspace()

    stale_failures = sum(1 for r in results if r.stale_recall_failure)
    passed = sum(1 for r in results if r.passed)
    verify_latencies = [r.verify_latency_ms for r in results if r.verify_latency_ms > 0]
    p95_verify = (
        statistics.quantiles(verify_latencies, n=20)[18]
        if len(verify_latencies) >= 20
        else (max(verify_latencies) if verify_latencies else 0.0)
    )
    avg_verify = statistics.mean(verify_latencies) if verify_latencies else 0.0

    summary: Dict[str, Any] = {
        "total_scenarios": len(results),
        "passed_scenarios": passed,
        "stale_recall_failures": stale_failures,
        "verify_latency_avg_ms": round(avg_verify, 3),
        "verify_latency_p95_ms": round(p95_verify, 3),
        "verify_p95_target_ms": VERIFY_P95_TARGET_MS,
        "stale_recall_target": 0,
        "all_passed": passed == len(results) and stale_failures == 0,
        "scenarios": [
            {
                "id": r.scenario_id,
                "description": r.description,
                "passed": r.passed,
                "stale_recall_failure": r.stale_recall_failure,
                "verify_latency_ms": round(r.verify_latency_ms, 3),
                "detail": r.detail,
            }
            for r in results
        ],
    }

    table = Table(title="🛡️ Context Rot Benchmark Results", header_style="bold magenta")
    table.add_column("Scenario", style="cyan", width=28)
    table.add_column("Pass", justify="center")
    table.add_column("Stale Leak", justify="center")
    table.add_column("Verify ms", justify="right")
    table.add_column("Detail", style="dim")

    for r in results:
        table.add_row(
            r.scenario_id,
            "[green]✓[/green]" if r.passed else "[red]✗[/red]",
            "[red]YES[/red]" if r.stale_recall_failure else "no",
            f"{r.verify_latency_ms:.2f}" if r.verify_latency_ms else "—",
            r.detail,
        )

    console.print(table)
    console.print(
        f"\n[bold]Summary:[/bold] {passed}/{len(results)} scenarios passed | "
        f"stale-recall failures: [bold]{stale_failures}[/bold] (target 0) | "
        f"verify p95: [bold]{p95_verify:.2f}ms[/bold] (target <{VERIFY_P95_TARGET_MS}ms)"
    )

    if output_markdown:
        _write_report(summary)
        console.print(f"\nReport saved to [cyan]{REPORT_PATH}[/cyan]")

    return summary


def _write_report(summary: Dict[str, Any]) -> None:
    rows = "\n".join(
        f"| **{s['id']}** | {'PASS' if s['passed'] else 'FAIL'} | "
        f"{'YES' if s['stale_recall_failure'] else 'no'} | "
        f"{s['verify_latency_ms'] or '—'} | {s['detail']} |"
        for s in summary["scenarios"]
    )
    stale_ok = summary["stale_recall_failures"] == 0
    verify_ok = summary["verify_latency_p95_ms"] < summary["verify_p95_target_ms"]
    md = f"""# 🔋 Battery — Context Rot Benchmark Report

**Scenarios:** {summary["total_scenarios"]} citation / prune rot cases\
**Target:** 0 stale-recall failures; JIT verify p95 < {summary["verify_p95_target_ms"]}ms

---

## Summary

| Metric | Result | Target | Status |
| :--- | :---: | :---: | :---: |
| **Scenarios passed** | **{summary["passed_scenarios"]}/{summary["total_scenarios"]}** | all | {'✅' if summary['all_passed'] else '❌'} |
| **Stale-recall failures** | **{summary["stale_recall_failures"]}** | 0 | {'✅' if stale_ok else '❌'} |
| **JIT verify p95 latency** | **{summary["verify_latency_p95_ms"]} ms** | < {summary["verify_p95_target_ms"]} ms | {'✅' if verify_ok else '❌'} |
| **JIT verify avg latency** | **{summary["verify_latency_avg_ms"]} ms** | — | — |

---

## Scenario Results

| Scenario | Pass | Stale Leak | Verify (ms) | Detail |
| :--- | :---: | :---: | :---: | :--- |
{rows}
"""
    REPORT_PATH.write_text(md, encoding="utf-8")
