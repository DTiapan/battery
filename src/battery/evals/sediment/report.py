"""Generate comparative benchmark report from Sediment raw JSON results."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from battery.evals.sediment.runner import sediment_root


def _latest_results(system: str) -> Path | None:
    raw_dir = sediment_root() / "results" / "raw"
    if not raw_dir.is_dir():
        return None
    matches = sorted(raw_dir.glob(f"{system}_results_*.json"), reverse=True)
    return matches[0] if matches else None


def _metric(phase: dict, key: str) -> float | None:
    metrics = phase.get("metrics", {})
    block = metrics.get(key, {})
    if isinstance(block, dict):
        return block.get("aggregate")
    return None


def build_comparative_report(systems: list[str]) -> str:
    rows: list[dict] = []
    for system in systems:
        path = _latest_results(system)
        if path is None:
            rows.append({"system": system, "skipped": True})
            continue
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        phase = data.get("phases", {}).get("retrieval", {})
        latency = phase.get("latency", {})
        store_p95 = (latency.get("store") or {}).get("p95")
        recall_p95 = (latency.get("recall") or {}).get("p95")
        rows.append(
            {
                "system": system,
                "skipped": False,
                "mrr": _metric(phase, "mrr"),
                "r5": _metric(phase, "recall_at_5"),
                "r1": _metric(phase, "recall_at_1"),
                "ndcg": _metric(phase, "ndcg_at_5"),
                "store_p95": store_p95,
                "recall_p95": recall_p95,
                "stored_count": phase.get("stored_count"),
                "store_errors": phase.get("store_errors"),
            }
        )

    lines = [
        "# Comparative Retrieval Benchmark — Tier 1 (Sediment)",
        "",
        f"**Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "**Harness:** sediment-benchmark (see docs/evals/SEDIMENT_PIN.md)",
        "**Dataset:** 1,000 memories · 200 queries",
        "",
        "## Retrieval (primary)",
        "",
        "| System | MRR | Recall@5 | Recall@1 | nDCG@5 | Store p95 ms | Recall p95 ms | Stored |",
        "|--------|----:|---------:|---------:|-------:|-------------:|--------------:|-------:|",
    ]

    for row in rows:
        if row.get("skipped"):
            lines.append(f"| {row['system']} | SKIPPED | — | — | — | — | — | — |")
            continue
        lines.append(
            "| {system} | {mrr} | {r5} | {r1} | {ndcg} | {sp95} | {rp95} | {stored} |".format(
                system=row["system"],
                mrr=f"{row['mrr']:.3f}" if row.get("mrr") is not None else "—",
                r5=f"{row['r5']:.3f}" if row.get("r5") is not None else "—",
                r1=f"{row['r1']:.3f}" if row.get("r1") is not None else "—",
                ndcg=f"{row['ndcg']:.3f}" if row.get("ndcg") is not None else "—",
                sp95=f"{row['store_p95'] * 1000:.1f}" if row.get("store_p95") is not None else "—",
                rp95=f"{row['recall_p95'] * 1000:.1f}" if row.get("recall_p95") is not None else "—",
                stored=str(row.get("stored_count", "—")),
            )
        )

    lines.extend(
        [
            "",
            "## Launch gate (manual)",
            "",
            "- [ ] G2a: Battery MRR ≥ max(memex, local-memory-mcp) OR within 0.01 @ lower p95",
            "- [ ] G2b: Battery Recall@5 ≥ ChromaDB (if run)",
            "- [ ] G2c: Zero ingest failures",
            "",
            "## Notes",
            "",
            "- Scores are only comparable within this harness run (same corpus + queries).",
            "- Systems marked SKIPPED were not run (missing binary or install failure).",
        ]
    )
    return "\n".join(lines)


def write_comparative_report(systems: list[str], out_path: Path | None = None) -> Path:
    if out_path is None:
        out_path = Path(__file__).resolve().parents[1] / "comparative_benchmark_report.md"
    out_path.write_text(build_comparative_report(systems), encoding="utf-8")

    results_json = out_path.with_name("comparative_benchmark_results.json")
    payload = {}
    for system in systems:
        path = _latest_results(system)
        if path:
            with open(path, encoding="utf-8") as handle:
                payload[system] = json.load(handle)
    results_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return out_path
