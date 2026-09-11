import json
import statistics
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from battery.db import get_connection, init_db, insert_memory
from battery.embeddings import embed_text
from battery.retrieval import hybrid_search, search_bm25, search_vector

console = Console()

EVALS_DIR = Path(__file__).parent
DATASET_PATH = EVALS_DIR / "dataset.json"
RESULTS_JSON_PATH = EVALS_DIR / "benchmark_results.json"
RESULTS_MD_PATH = EVALS_DIR / "benchmark_results.md"

def load_dataset(dataset_path: Path = DATASET_PATH) -> Dict[str, Any]:
    with open(dataset_path, "r", encoding="utf-8") as f:
        return json.load(f)

def run_evaluation(
    dataset: Optional[Dict[str, Any]] = None,
    output_markdown: bool = True,
    output_json: bool = True,
) -> Dict[str, Any]:
    """Runs the retrieval evaluation comparing BM25, Dense Vector, and Battery Hybrid (RRF)."""
    if dataset is None:
        dataset = load_dataset()

    corpus = dataset["corpus"]
    queries = dataset["queries"]

    # Use a clean temporary in-memory database for evaluation
    conn = get_connection(Path(":memory:"))
    init_db(conn)

    console.print(f"[bold cyan]⚡ Seeding evaluation corpus ({len(corpus)} records)...[/bold cyan]")
    start_seed = time.perf_counter()
    for item in corpus:
        vec = embed_text(item["content"])
        insert_memory(
            conn,
            item["content"],
            vec,
            category=item["category"],
            importance=item.get("importance", 1.0),
        )
    seed_time = (time.perf_counter() - start_seed) * 1000
    console.print(f"[green]✓ Corpus seeded in {seed_time:.1f}ms[/green]\n")

    methods = ["BM25 (FTS5)", "Vector (sqlite-vec)", "Battery Hybrid (RRF)"]
    metrics: Dict[str, Dict[str, Any]] = {
        m: {
            "hits_at_1": 0,
            "hits_at_3": 0,
            "hits_at_5": 0,
            "mrr_sum": 0.0,
            "latencies_ms": [],
            "by_type": {},
        }
        for m in methods
    }

    query_types = sorted(list(set(q["type"] for q in queries)))
    for m in methods:
        for q_type in query_types:
            metrics[m]["by_type"][q_type] = {
                "count": 0,
                "hits_at_1": 0,
                "hits_at_3": 0,
                "hits_at_5": 0,
                "mrr_sum": 0.0,
            }

    # Execute queries across all 3 methods
    for q in queries:
        query_text = q["query"]
        expected_ids = set(q["expected_memory_ids"])
        category = q.get("category")
        q_type = q["type"]

        # 1. BM25
        t0 = time.perf_counter()
        bm25_res = search_bm25(conn, query_text, limit=5, category=category)
        bm25_lat = (time.perf_counter() - t0) * 1000

        # 2. Vector
        t0 = time.perf_counter()
        vec_res = search_vector(conn, query_text, limit=5, category=category)
        vec_lat = (time.perf_counter() - t0) * 1000

        # 3. Hybrid
        t0 = time.perf_counter()
        hyb_res = hybrid_search(conn, query_text, limit=5, category=category)
        hyb_lat = (time.perf_counter() - t0) * 1000

        runs = [
            ("BM25 (FTS5)", bm25_res, bm25_lat),
            ("Vector (sqlite-vec)", vec_res, vec_lat),
            ("Battery Hybrid (RRF)", hyb_res, hyb_lat),
        ]

        for method_name, results, latency in runs:
            m_data = metrics[method_name]
            m_data["latencies_ms"].append(latency)

            result_ids = [r["id"] for r in results]
            hit_rank = 0
            for idx, r_id in enumerate(result_ids):
                if r_id in expected_ids:
                    hit_rank = idx + 1
                    break

            if hit_rank == 1:
                m_data["hits_at_1"] += 1
                m_data["by_type"][q_type]["hits_at_1"] += 1
            if hit_rank > 0 and hit_rank <= 3:
                m_data["hits_at_3"] += 1
                m_data["by_type"][q_type]["hits_at_3"] += 1
            if hit_rank > 0 and hit_rank <= 5:
                m_data["hits_at_5"] += 1
                m_data["by_type"][q_type]["hits_at_5"] += 1

            reciprocal_rank = 1.0 / hit_rank if hit_rank > 0 else 0.0
            m_data["mrr_sum"] += reciprocal_rank
            m_data["by_type"][q_type]["mrr_sum"] += reciprocal_rank
            m_data["by_type"][q_type]["count"] += 1

    conn.close()

    total_queries = len(queries)
    summary: Dict[str, Any] = {}
    for m in methods:
        latencies = metrics[m]["latencies_ms"]
        p50 = statistics.median(latencies) if latencies else 0.0
        p95 = statistics.quantiles(latencies, n=20)[18] if len(latencies) >= 20 else max(latencies)
        avg_lat = statistics.mean(latencies) if latencies else 0.0

        summary[m] = {
            "Hit@1": round(metrics[m]["hits_at_1"] / total_queries, 4),
            "Hit@3": round(metrics[m]["hits_at_3"] / total_queries, 4),
            "Hit@5": round(metrics[m]["hits_at_5"] / total_queries, 4),
            "MRR": round(metrics[m]["mrr_sum"] / total_queries, 4),
            "Latency_Avg_ms": round(avg_lat, 2),
            "Latency_P50_ms": round(p50, 2),
            "Latency_P95_ms": round(p95, 2),
            "by_type": {},
        }
        for q_type in query_types:
            type_count = metrics[m]["by_type"][q_type]["count"]
            summary[m]["by_type"][q_type] = {
                "Hit@1": round(metrics[m]["by_type"][q_type]["hits_at_1"] / type_count, 4),
                "Hit@3": round(metrics[m]["by_type"][q_type]["hits_at_3"] / type_count, 4),
                "MRR": round(metrics[m]["by_type"][q_type]["mrr_sum"] / type_count, 4),
            }

    # Render Rich Table
    table = Table(title=f"🔋 Battery Retrieval Evaluation — Overall Benchmark ({total_queries} Queries)", header_style="bold magenta")
    table.add_column("Retrieval Strategy", style="bold cyan", width=24)
    table.add_column("Hit@1", justify="center")
    table.add_column("Hit@3", justify="center")
    table.add_column("Hit@5", justify="center")
    table.add_column("MRR", justify="center", style="bold yellow")
    table.add_column("Avg Latency", justify="right")
    table.add_column("p50 Latency", justify="right")
    table.add_column("p95 Latency", justify="right")

    for m in methods:
        s = summary[m]
        is_hybrid = "Hybrid" in m
        style_color = "bold green" if is_hybrid else "white"
        table.add_row(
            f"[{style_color}]{m}[/{style_color}]",
            f"[{style_color}]{s['Hit@1'] * 100:.1f}%[/{style_color}]",
            f"[{style_color}]{s['Hit@3'] * 100:.1f}%[/{style_color}]",
            f"[{style_color}]{s['Hit@5'] * 100:.1f}%[/{style_color}]",
            f"[{style_color}]{s['MRR']:.4f}[/{style_color}]",
            f"{s['Latency_Avg_ms']:.1f}ms",
            f"{s['Latency_P50_ms']:.1f}ms",
            f"{s['Latency_P95_ms']:.1f}ms",
        )

    console.print(table)
    console.print("")

    # Query Type Breakdown Table
    slice_table = Table(title="📊 Performance Sliced by Query Intent", header_style="bold blue")
    slice_table.add_column("Query Intent", style="bold", width=20)
    slice_table.add_column("Method", width=22)
    slice_table.add_column("Hit@1", justify="center")
    slice_table.add_column("Hit@3", justify="center")
    slice_table.add_column("MRR", justify="center")

    for q_type in query_types:
        for m in methods:
            t_data = summary[m]["by_type"][q_type]
            is_hyb = "Hybrid" in m
            c = "green" if is_hyb else "white"
            slice_table.add_row(
                q_type.replace("_", " ").title(),
                f"[{c}]{m}[/{c}]",
                f"[{c}]{t_data['Hit@1'] * 100:.0f}%[/{c}]",
                f"[{c}]{t_data['Hit@3'] * 100:.0f}%[/{c}]",
                f"[{c}]{t_data['MRR']:.3f}[/{c}]",
            )

    console.print(slice_table)

    # Save to JSON
    if output_json:
        RESULTS_JSON_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        console.print(f"\n[dim]Saved benchmark data to {RESULTS_JSON_PATH}[/dim]")

    # Save to Markdown
    if output_markdown:
        md_content = f"""# 🔋 Battery Context Engine — Retrieval Benchmark Results

**Date:** {time.strftime('%Y-%m-%d')}  
**Evaluation Queries:** {total_queries}  
**Corpus Size:** {len(corpus)} items  

## Overall Retrieval Performance

| Retrieval Strategy | Hit@1 | Hit@3 | Hit@5 | MRR | Avg Latency | p50 Latency |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
"""
        for m in methods:
            s = summary[m]
            md_content += f"| **{m}** | **{s['Hit@1'] * 100:.1f}%** | **{s['Hit@3'] * 100:.1f}%** | **{s['Hit@5'] * 100:.1f}%** | **{s['MRR']:.4f}** | {s['Latency_Avg_ms']:.1f}ms | {s['Latency_P50_ms']:.1f}ms |\n"

        md_content += "\n## Performance by Query Intent\n\n"
        md_content += "| Query Intent | Method | Hit@1 | Hit@3 | MRR |\n| :--- | :--- | :---: | :---: | :---: |\n"
        for q_type in query_types:
            for m in methods:
                t_data = summary[m]["by_type"][q_type]
                md_content += f"| {q_type.replace('_', ' ').title()} | {m} | {t_data['Hit@1'] * 100:.0f}% | {t_data['Hit@3'] * 100:.0f}% | {t_data['MRR']:.3f} |\n"

        RESULTS_MD_PATH.write_text(md_content, encoding="utf-8")
        console.print(f"[dim]Generated Markdown report to {RESULTS_MD_PATH}[/dim]")

    return summary

if __name__ == "__main__":
    run_evaluation()
