"""Battery Context Engine — Real-World Retrieval Evaluation Harness.

Evaluates BM25, Vector, and Battery Hybrid on a corpus of real engineering
memories extracted from Battery's own ADRs, README, and docstrings.
Ground truth is matched by content substring tag (future-proof, not integer IDs).
"""

import statistics
import time
from pathlib import Path
from typing import Any, Dict, List

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from battery.db import get_connection, init_db, insert_memories_batch
from battery.embeddings import embed_batch
from battery.evals.generate_realworld_data import get_realworld_dataset
from battery.retrieval import hybrid_search, search_bm25, search_vector

console = Console()
REALWORLD_REPORT_PATH = Path(__file__).parent / "realworld_benchmark_report.md"


def run_realworld_evaluation(output_markdown: bool = True) -> Dict[str, Any]:
    """Runs BM25 / Vector / Hybrid evaluation on the real-world corpus."""
    dataset = get_realworld_dataset()
    corpus = dataset["corpus"]
    queries = dataset["queries"]

    console.print(
        Panel.fit(
            "[bold cyan]🔋 Battery — Real-World Retrieval Evaluation[/bold cyan]\n"
            f"Corpus:  [bold]{len(corpus)} genuine engineering memories[/bold] "
            "(Battery ADRs, README, docstrings, curated rules)\n"
            f"Queries: [bold]{len(queries)} authentic developer / LLM agent queries[/bold]\n"
            "Engine:  [bold]SQLite WAL + FTS5 + sqlite-vec (ONNX all-MiniLM-L6-v2)[/bold]",
            title="Real-World Eval Configuration",
        )
    )

    # ── Ingest ─────────────────────────────────────────────────────────────
    temp_db_path = Path(__file__).parent / "temp_realworld.db"

    def cleanup() -> None:
        for suffix in ("", "-wal", "-shm"):
            p = temp_db_path.with_name(temp_db_path.name + suffix)
            if p.exists():
                try:
                    p.unlink()
                except OSError:
                    pass

    cleanup()
    conn = get_connection(temp_db_path)
    init_db(conn)

    console.print(f"[cyan]⚡ Embedding and indexing {len(corpus)} real-world memories...[/cyan]")
    t0 = time.perf_counter()
    texts = [item["content"] for item in corpus]
    vectors = embed_batch(texts)
    items = [
        {
            "content": item["content"],
            "embedding": vec,
            "category": item["category"],
            "importance": item["importance"],
        }
        for item, vec in zip(corpus, vectors)
    ]
    inserted = insert_memories_batch(conn, items)
    ingest_ms = (time.perf_counter() - t0) * 1000

    # Map content → DB id (needed since insert may dedup)
    cur = conn.execute("SELECT id, content FROM memories WHERE is_deleted = 0")
    content_to_db_id: Dict[str, int] = {row["content"].strip(): row["id"] for row in cur.fetchall()}
    tag_to_db_id: Dict[str, int] = {}
    for item in corpus:
        db_id = content_to_db_id.get(item["content"].strip())
        if db_id:
            tag_to_db_id[item["ground_truth_tag"]] = db_id

    console.print(f"[green]✓ Indexed {inserted} memories in {ingest_ms:.0f}ms[/green]\n")

    # ── Evaluation Loop ────────────────────────────────────────────────────
    methods = ["BM25 (FTS5)", "Vector (sqlite-vec)", "Battery Hybrid (RRF)"]
    metrics: Dict[str, Dict[str, Any]] = {
        m: {
            "h1": 0,
            "h3": 0,
            "h5": 0,
            "mrr_sum": 0.0,
            "latencies": [],
            "by_type": {},
        }
        for m in methods
    }
    query_types = sorted({q["type"] for q in queries})
    for m in methods:
        for qt in query_types:
            metrics[m]["by_type"][qt] = {"count": 0, "h1": 0, "h3": 0, "h5": 0, "mrr_sum": 0.0}

    miss_log: List[Dict[str, Any]] = []

    for q in queries:
        q_text = q["query"]
        q_type = q["type"]
        expected_ids = [tag_to_db_id[tag] for tag in q["expected_tags"] if tag in tag_to_db_id]
        expected_set = set(expected_ids)

        t_bm = time.perf_counter()
        bm25_res = search_bm25(conn, q_text, limit=5)
        bm25_lat = (time.perf_counter() - t_bm) * 1000

        t_vec = time.perf_counter()
        vec_res = search_vector(conn, q_text, limit=5)
        vec_lat = (time.perf_counter() - t_vec) * 1000

        t_hyb = time.perf_counter()
        hyb_res = hybrid_search(conn, q_text, limit=5)
        hyb_lat = (time.perf_counter() - t_hyb) * 1000

        for method_name, results, latency in [
            ("BM25 (FTS5)", bm25_res, bm25_lat),
            ("Vector (sqlite-vec)", vec_res, vec_lat),
            ("Battery Hybrid (RRF)", hyb_res, hyb_lat),
        ]:
            m_data = metrics[method_name]
            m_data["latencies"].append(latency)
            result_ids = [r["id"] for r in results]

            hit_rank = 0
            for idx, r_id in enumerate(result_ids):
                if r_id in expected_set:
                    hit_rank = idx + 1
                    break

            if hit_rank == 1:
                m_data["h1"] += 1
                m_data["by_type"][q_type]["h1"] += 1
            if 0 < hit_rank <= 3:
                m_data["h3"] += 1
                m_data["by_type"][q_type]["h3"] += 1
            if 0 < hit_rank <= 5:
                m_data["h5"] += 1
                m_data["by_type"][q_type]["h5"] += 1

            rr = 1.0 / hit_rank if hit_rank > 0 else 0.0
            m_data["mrr_sum"] += rr
            m_data["by_type"][q_type]["mrr_sum"] += rr
            m_data["by_type"][q_type]["count"] += 1

            if hit_rank == 0 and method_name == "Battery Hybrid (RRF)":
                miss_log.append(
                    {"query": q_text, "expected_tags": q["expected_tags"], "got": result_ids[:3]}
                )

    conn.close()
    cleanup()

    # ── Build summary ──────────────────────────────────────────────────────
    total_q = len(queries)
    summary: Dict[str, Any] = {"total_queries": total_q, "corpus_size": len(corpus), "methods": {}}

    for m in methods:
        lats = metrics[m]["latencies"]
        p50 = statistics.median(lats) if lats else 0.0
        p95 = statistics.quantiles(lats, n=20)[18] if len(lats) >= 20 else max(lats)
        avg = statistics.mean(lats) if lats else 0.0
        summary["methods"][m] = {
            "Hit@1": round(metrics[m]["h1"] / total_q, 4),
            "Hit@3": round(metrics[m]["h3"] / total_q, 4),
            "Hit@5": round(metrics[m]["h5"] / total_q, 4),
            "MRR": round(metrics[m]["mrr_sum"] / total_q, 4),
            "Latency_Avg_ms": round(avg, 2),
            "Latency_P50_ms": round(p50, 2),
            "Latency_P95_ms": round(p95, 2),
            "by_type": {},
        }
        for qt in query_types:
            cnt = metrics[m]["by_type"][qt]["count"]
            summary["methods"][m]["by_type"][qt] = {
                "Hit@1": round(metrics[m]["by_type"][qt]["h1"] / cnt, 4) if cnt else 0.0,
                "Hit@3": round(metrics[m]["by_type"][qt]["h3"] / cnt, 4) if cnt else 0.0,
                "MRR": round(metrics[m]["by_type"][qt]["mrr_sum"] / cnt, 4) if cnt else 0.0,
            }

    # ── Render overall table ───────────────────────────────────────────────
    bench_table = Table(
        title=f"🔋 Real-World Retrieval Benchmark — {len(corpus)} Memories, {total_q} Queries",
        header_style="bold magenta",
    )
    bench_table.add_column("Strategy", style="bold cyan", width=24)
    bench_table.add_column("Hit@1", justify="center")
    bench_table.add_column("Hit@3", justify="center")
    bench_table.add_column("Hit@5", justify="center")
    bench_table.add_column("MRR", justify="center", style="bold yellow")
    bench_table.add_column("Avg Latency", justify="right")
    bench_table.add_column("p50", justify="right")
    bench_table.add_column("p95", justify="right")

    for m in methods:
        s = summary["methods"][m]
        is_hyb = "Hybrid" in m
        color = "bold green" if is_hyb else "white"
        bench_table.add_row(
            f"[{color}]{m}[/{color}]",
            f"[{color}]{s['Hit@1'] * 100:.1f}%[/{color}]",
            f"[{color}]{s['Hit@3'] * 100:.1f}%[/{color}]",
            f"[{color}]{s['Hit@5'] * 100:.1f}%[/{color}]",
            f"[{color}]{s['MRR']:.4f}[/{color}]",
            f"{s['Latency_Avg_ms']:.1f}ms",
            f"{s['Latency_P50_ms']:.1f}ms",
            f"{s['Latency_P95_ms']:.1f}ms",
        )
    console.print(bench_table)
    console.print("")

    # ── Sliced by query type ───────────────────────────────────────────────
    slice_table = Table(title="📊 Recall Sliced by Query Intent", header_style="bold blue")
    slice_table.add_column("Query Intent", style="bold", width=20)
    slice_table.add_column("Method", width=24)
    slice_table.add_column("Hit@1", justify="center")
    slice_table.add_column("Hit@3", justify="center")
    slice_table.add_column("MRR", justify="center")
    for qt in query_types:
        for m in methods:
            t_data = summary["methods"][m]["by_type"][qt]
            is_hyb = "Hybrid" in m
            c = "green" if is_hyb else "white"
            slice_table.add_row(
                qt.replace("_", " ").title(),
                f"[{c}]{m}[/{c}]",
                f"[{c}]{t_data['Hit@1'] * 100:.0f}%[/{c}]",
                f"[{c}]{t_data['Hit@3'] * 100:.0f}%[/{c}]",
                f"[{c}]{t_data['MRR']:.3f}[/{c}]",
            )
    console.print(slice_table)

    # ── Miss log ───────────────────────────────────────────────────────────
    if miss_log:
        console.print(f"\n[yellow]⚠️  Battery Hybrid missed {len(miss_log)} queries:[/yellow]")
        for miss in miss_log:
            console.print(f"  • [dim]{miss['query'][:80]}[/dim] → expected {miss['expected_tags']}")

    # ── Markdown Report ────────────────────────────────────────────────────
    if output_markdown:
        md = f"""# 🔋 Battery — Real-World Retrieval Benchmark

**Corpus:** {len(corpus)} genuine engineering memories (Battery ADRs, README, docstrings, curated rules)\\
**Queries:** {total_q} authentic developer / LLM agent queries\\
**Engine:** SQLite WAL + FTS5 BM25 + sqlite-vec ONNX `all-MiniLM-L6-v2`

---

## Overall Retrieval Performance

| Retrieval Strategy | Hit@1 | Hit@3 | Hit@5 | MRR | Avg Latency | p50 Latency | p95 Latency |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
"""
        for m in methods:
            s = summary["methods"][m]
            md += (
                f"| **{m}** | **{s['Hit@1'] * 100:.1f}%** | **{s['Hit@3'] * 100:.1f}%** | "
                f"**{s['Hit@5'] * 100:.1f}%** | **{s['MRR']:.4f}** | "
                f"{s['Latency_Avg_ms']:.1f}ms | {s['Latency_P50_ms']:.1f}ms | {s['Latency_P95_ms']:.1f}ms |\n"
            )
        md += "\n## Performance by Query Intent\n\n"
        md += "| Query Intent | Method | Hit@1 | Hit@3 | MRR |\n| :--- | :--- | :---: | :---: | :---: |\n"
        for qt in query_types:
            for m in methods:
                t = summary["methods"][m]["by_type"][qt]
                md += f"| {qt.replace('_', ' ').title()} | {m} | {t['Hit@1'] * 100:.0f}% | {t['Hit@3'] * 100:.0f}% | {t['MRR']:.3f} |\n"
        REALWORLD_REPORT_PATH.write_text(md, encoding="utf-8")
        console.print(f"\n[dim]Report saved to {REALWORLD_REPORT_PATH}[/dim]")

    return summary
