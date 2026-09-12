"""Battery Context Engine — Near-Duplicate Re-Ingest Stress Benchmark.

Measures row bloat prevention on repeated capture (NEXT-2) and checks that
stress-suite hybrid MRR does not regress after paraphrase re-ingestion.
"""

from pathlib import Path
from typing import Any, Dict, List, Tuple

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from battery.db import get_connection, init_db, insert_memories_batch, insert_memory
from battery.embeddings import embed_batch, embed_text
from battery.evals.generate_stress_data import get_stress_dataset
from battery.retrieval import hybrid_search

console = Console()

REPORT_PATH = Path(__file__).parent / "dedup_stress_report.md"
DUP_REDUCTION_TARGET = 0.40
REINGEST_FRACTION = 0.40
MRR_REGRESSION_TOLERANCE = 0.001


def paraphrase_content(content: str, idx: int) -> str:
    """Produces a semantic paraphrase likely to exceed NEAR_DUP_THRESHOLD."""
    variants = [
        lambda s: s.replace("must", "should", 1),
        lambda s: f"Engineering standard: {s}",
        lambda s: s.replace("Always", "Teams should always", 1),
        lambda s: s.replace("Never", "Do not", 1),
        lambda s: "Updated policy — " + s[0].lower() + s[1:] if len(s) > 1 else s,
    ]
    rewritten = variants[idx % len(variants)](content)
    return rewritten if rewritten != content else f"Revised guidance: {content}"


def _eligible_items(corpus: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [c for c in corpus if c["category"] in {"rule", "decision", "preference", "general"}]


def _reingest_candidates(
    eligible: List[Dict[str, Any]],
    queries: List[Dict[str, Any]],
    reingest_count: int,
) -> List[Dict[str, Any]]:
    """Pick paraphrase re-ingest items that are not retrieval eval targets."""
    protected_ids = {mem_id for q in queries for mem_id in q["expected_ids"]}
    pool = [item for item in eligible if item["id"] not in protected_ids]
    return pool[:reingest_count]


def _active_row_count(conn) -> int:
    row = conn.execute("SELECT COUNT(*) AS n FROM memories WHERE is_deleted = 0").fetchone()
    return int(row["n"])


def _seed_corpus(conn, corpus: List[Dict[str, Any]], *, near_dedup: bool) -> None:
    texts = [c["content"] for c in corpus]
    vectors = embed_batch(texts)
    if near_dedup:
        for item, vec in zip(corpus, vectors):
            insert_memory(
                conn,
                item["content"],
                vec,
                category=item["category"],
                importance=item.get("importance", 1.0),
                near_dedup=True,
            )
    else:
        items = [
            {
                "content": item["content"],
                "embedding": vec,
                "category": item["category"],
                "importance": item.get("importance", 1.0),
            }
            for item, vec in zip(corpus, vectors)
        ]
        insert_memories_batch(conn, items)
    conn.commit()


def _hybrid_mrr(conn, queries: List[Dict[str, Any]]) -> float:
    mrr_sum = 0.0
    for q in queries:
        expected = set(q["expected_ids"])
        results = hybrid_search(conn, q["query"], limit=5, verify=False)
        hit = next((i + 1 for i, row in enumerate(results) if row["id"] in expected), 0)
        mrr_sum += 1.0 / hit if hit else 0.0
    return mrr_sum / len(queries) if queries else 0.0


def _reingest_paraphrases(
    conn,
    items: List[Dict[str, Any]],
    *,
    near_dedup: bool,
) -> Tuple[int, int]:
    """Re-ingests paraphrases; returns (attempted, merged_or_existing)."""
    attempted = 0
    prevented = 0
    for idx, item in enumerate(items):
        paraphrase = paraphrase_content(item["content"], idx)
        vec = embed_text(paraphrase)
        result = insert_memory(
            conn,
            paraphrase,
            vec,
            category=item["category"],
            importance=item.get("importance", 1.0),
            near_dedup=near_dedup,
        )
        attempted += 1
        if result["status"] in {"merged", "existing"}:
            prevented += 1
    conn.commit()
    return attempted, prevented


def run_dedup_stress_benchmark(
    scale: int = 500,
    output_markdown: bool = True,
) -> Dict[str, Any]:
    """Runs near-dup re-ingest stress benchmark on the scaled stress corpus."""
    dataset = get_stress_dataset(scale=scale)
    corpus = dataset["corpus"]
    queries = dataset["queries"]
    eligible = _eligible_items(corpus)
    protected_ids = {mem_id for q in queries for mem_id in q["expected_ids"]}
    pool_size = len([c for c in eligible if c["id"] not in protected_ids])
    reingest_count = max(1, min(int(len(eligible) * REINGEST_FRACTION), pool_size))
    reingest_items = _reingest_candidates(eligible, queries, reingest_count)

    console.print(
        Panel.fit(
            "[bold cyan]🔋 Battery Near-Duplicate Re-Ingest Stress Benchmark[/bold cyan]\n"
            f"Corpus:       [bold]{len(corpus)}[/bold] memories\n"
            f"Re-ingest:    [bold]{reingest_count}[/bold] paraphrases ({REINGEST_FRACTION:.0%} of eligible)\n"
            f"Targets:      duplicate reduction ≥ {DUP_REDUCTION_TARGET:.0%}, MRR non-regression",
            title="Dedup Stress Configuration",
        )
    )

    # Baseline MRR on freshly seeded corpus (dedup enabled)
    baseline_conn = get_connection(Path(":memory:"))
    init_db(baseline_conn)
    _seed_corpus(baseline_conn, corpus, near_dedup=True)
    baseline_mrr = _hybrid_mrr(baseline_conn, queries)
    baseline_conn.close()

    # Naive re-ingest path (no near-dedup on paraphrases)
    naive_conn = get_connection(Path(":memory:"))
    init_db(naive_conn)
    _seed_corpus(naive_conn, corpus, near_dedup=False)
    naive_before = _active_row_count(naive_conn)
    naive_attempted, _ = _reingest_paraphrases(naive_conn, reingest_items, near_dedup=False)
    naive_after = _active_row_count(naive_conn)
    naive_extra_rows = naive_after - naive_before
    naive_post_mrr = _hybrid_mrr(naive_conn, queries)
    naive_conn.close()

    # Dedup-enabled re-ingest path
    dedup_conn = get_connection(Path(":memory:"))
    init_db(dedup_conn)
    _seed_corpus(dedup_conn, corpus, near_dedup=True)
    dedup_before = _active_row_count(dedup_conn)
    dedup_attempted, dedup_prevented = _reingest_paraphrases(
        dedup_conn, reingest_items, near_dedup=True
    )
    dedup_after = _active_row_count(dedup_conn)
    dedup_extra_rows = dedup_after - dedup_before
    post_mrr = _hybrid_mrr(dedup_conn, queries)
    dedup_conn.close()

    duplicate_rows_prevented = naive_extra_rows - dedup_extra_rows
    reduction_rate = duplicate_rows_prevented / naive_extra_rows if naive_extra_rows else 0.0
    merge_rate = dedup_prevented / dedup_attempted if dedup_attempted else 0.0
    mrr_delta_vs_baseline = post_mrr - baseline_mrr
    mrr_delta_vs_naive = post_mrr - naive_post_mrr
    mrr_ok = mrr_delta_vs_naive >= -MRR_REGRESSION_TOLERANCE
    reduction_ok = reduction_rate >= DUP_REDUCTION_TARGET

    summary: Dict[str, Any] = {
        "scale": scale,
        "corpus_size": len(corpus),
        "reingest_attempts": dedup_attempted,
        "naive_extra_rows": naive_extra_rows,
        "dedup_extra_rows": dedup_extra_rows,
        "duplicate_rows_prevented": duplicate_rows_prevented,
        "duplicate_reduction_rate": round(reduction_rate, 4),
        "duplicate_reduction_target": DUP_REDUCTION_TARGET,
        "merge_rate": round(merge_rate, 4),
        "baseline_hybrid_mrr": round(baseline_mrr, 4),
        "naive_post_reingest_mrr": round(naive_post_mrr, 4),
        "post_reingest_hybrid_mrr": round(post_mrr, 4),
        "mrr_delta_vs_baseline": round(mrr_delta_vs_baseline, 4),
        "mrr_delta_vs_naive": round(mrr_delta_vs_naive, 4),
        "reduction_pass": reduction_ok,
        "mrr_pass": mrr_ok,
        "all_passed": reduction_ok and mrr_ok,
    }

    table = Table(title="📉 Near-Duplicate Re-Ingest Stress Results", header_style="bold magenta")
    table.add_column("Metric", style="cyan", width=34)
    table.add_column("Value", justify="right")
    table.add_column("Target", justify="right")
    table.add_column("Pass", justify="center")

    def pass_cell(ok: bool) -> str:
        return "[green]✓[/green]" if ok else "[red]✗[/red]"

    table.add_row(
        "Naive extra rows (no near-dedup)",
        str(naive_extra_rows),
        "—",
        "—",
    )
    table.add_row(
        "Dedup extra rows (near-dedup on)",
        str(dedup_extra_rows),
        "≪ naive",
        pass_cell(dedup_extra_rows < naive_extra_rows),
    )
    table.add_row(
        "Duplicate row reduction",
        f"{reduction_rate * 100:.1f}%",
        f"≥ {DUP_REDUCTION_TARGET * 100:.0f}%",
        pass_cell(reduction_ok),
    )
    table.add_row(
        "Paraphrase merge rate",
        f"{merge_rate * 100:.1f}%",
        "—",
        "—",
    )
    table.add_row(
        "Baseline hybrid MRR (pre re-ingest)",
        f"{baseline_mrr:.4f}",
        "—",
        "—",
    )
    table.add_row(
        "Naive post re-ingest hybrid MRR",
        f"{naive_post_mrr:.4f}",
        "—",
        "—",
    )
    table.add_row(
        "Dedup post re-ingest hybrid MRR",
        f"{post_mrr:.4f}",
        f"≥ {naive_post_mrr - MRR_REGRESSION_TOLERANCE:.4f}",
        pass_cell(mrr_ok),
    )

    console.print(table)
    console.print(
        f"\n[bold]Summary:[/bold] prevented [bold]{duplicate_rows_prevented}[/bold] duplicate rows "
        f"({reduction_rate * 100:.1f}% reduction) | dedup MRR {post_mrr:.4f} vs naive {naive_post_mrr:.4f} "
        f"({mrr_delta_vs_naive:+.4f})"
    )

    if output_markdown:
        _write_report(summary)
        console.print(f"\nReport saved to [cyan]{REPORT_PATH}[/cyan]")

    return summary


def _write_report(summary: Dict[str, Any]) -> None:
    md = f"""# 🔋 Battery — Near-Duplicate Re-Ingest Stress Report

**Corpus:** {summary["corpus_size"]} memories\
**Re-ingest paraphrases:** {summary["reingest_attempts"]}\
**Targets:** ≥ {summary["duplicate_reduction_target"] * 100:.0f}% duplicate row reduction; no hybrid MRR regression

---

## Summary

| Metric | Result | Target | Status |
| :--- | :---: | :---: | :---: |
| **Naive extra rows** | **{summary["naive_extra_rows"]}** | — | — |
| **Dedup extra rows** | **{summary["dedup_extra_rows"]}** | ≪ naive | {"✅" if summary["dedup_extra_rows"] < summary["naive_extra_rows"] else "❌"} |
| **Duplicate row reduction** | **{summary["duplicate_reduction_rate"] * 100:.1f}%** | ≥ {summary["duplicate_reduction_target"] * 100:.0f}% | {"✅" if summary["reduction_pass"] else "❌"} |
| **Paraphrase merge rate** | **{summary["merge_rate"] * 100:.1f}%** | — | — |
| **Baseline hybrid MRR (pre re-ingest)** | **{summary["baseline_hybrid_mrr"]}** | — | — |
| **Naive post re-ingest hybrid MRR** | **{summary["naive_post_reingest_mrr"]}** | — | — |
| **Dedup post re-ingest hybrid MRR** | **{summary["post_reingest_hybrid_mrr"]}** | ≥ {summary["naive_post_reingest_mrr"] - MRR_REGRESSION_TOLERANCE:.4f} | {"✅" if summary["mrr_pass"] else "❌"} |
| **MRR delta vs naive re-ingest** | **{summary["mrr_delta_vs_naive"]:+.4f}** | ≥ -{MRR_REGRESSION_TOLERANCE} | {"✅" if summary["mrr_pass"] else "❌"} |
"""
    REPORT_PATH.write_text(md, encoding="utf-8")
