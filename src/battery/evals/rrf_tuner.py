"""Battery Context Engine — RRF Parameter Grid Sweep Tuner.

Empirically finds the optimal Reciprocal Rank Fusion k constant and text/vector
weight combination for Battery's hybrid retrieval on the real-world corpus.

The academic default is k=60 (tuned for TREC/MS-MARCO document retrieval).
For short factual memory assertions (1–3 sentences), a lower k provides more
signal from rank positions and is expected to outperform k=60.

Usage:
    uv run battery eval --tune
    uv run python -m battery.evals.rrf_tuner
"""

import statistics
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from battery.db import get_connection, init_db, insert_memories_batch
from battery.embeddings import embed_batch
from battery.evals.generate_realworld_data import get_realworld_dataset
from battery.retrieval import hybrid_search, search_bm25, search_vector

console = Console()

TUNER_REPORT_PATH = Path(__file__).parent / "rrf_tuning_report.md"

# Parameter grid to sweep
K_VALUES: List[int] = [5, 10, 20, 30, 40, 60]
TEXT_WEIGHTS: List[float] = [0.3, 0.4, 0.5, 0.6, 0.7]


def _build_ground_truth_ids(
    corpus: List[Dict[str, Any]],
    expected_tags: List[str],
) -> List[int]:
    """Resolves expected corpus IDs from ground_truth_tag substrings."""
    tag_to_id = {item["ground_truth_tag"]: item["id"] for item in corpus}
    return [tag_to_id[tag] for tag in expected_tags if tag in tag_to_id]


def _score_results(
    result_ids: List[int],
    expected_ids: List[int],
) -> Tuple[int, int, int, float]:
    """Returns (hit@1, hit@3, hit@5, reciprocal_rank) for a single query."""
    expected_set = set(expected_ids)
    hit_rank = 0
    for idx, r_id in enumerate(result_ids[:5]):
        if r_id in expected_set:
            hit_rank = idx + 1
            break

    h1 = 1 if hit_rank == 1 else 0
    h3 = 1 if 0 < hit_rank <= 3 else 0
    h5 = 1 if 0 < hit_rank <= 5 else 0
    rr = 1.0 / hit_rank if hit_rank > 0 else 0.0
    return h1, h3, h5, rr


def run_rrf_tuner(output_markdown: bool = True) -> Dict[str, Any]:
    """Runs the full RRF parameter sweep and returns the sorted results."""
    dataset = get_realworld_dataset()
    corpus = dataset["corpus"]
    queries = dataset["queries"]

    console.print(
        Panel.fit(
            "[bold cyan]⚙️  Battery RRF Parameter Grid Sweep[/bold cyan]\n"
            f"Corpus:    [bold]{len(corpus)} real-world memories[/bold] (ADRs, README, docstrings)\n"
            f"Queries:   [bold]{len(queries)} real developer queries[/bold]\n"
            f"k values:  [bold]{K_VALUES}[/bold]\n"
            f"Weights:   [bold]text {TEXT_WEIGHTS} / vec complement[/bold]\n"
            f"Grid size: [bold]{len(K_VALUES) * len(TEXT_WEIGHTS)} combinations[/bold]",
            title="RRF Tuner Configuration",
        )
    )

    # ── Seed the temp DB ───────────────────────────────────────────────────
    temp_db_path = Path(__file__).parent / "temp_tuner.db"

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

    # Re-fetch actual IDs from DB (may differ from corpus idx due to dedup)
    cursor = conn.execute("SELECT id, content FROM memories WHERE is_deleted = 0")
    content_to_db_id: Dict[str, int] = {
        row["content"].strip(): row["id"] for row in cursor.fetchall()
    }
    for item in corpus:
        item["db_id"] = content_to_db_id.get(item["content"].strip(), item["id"])

    console.print(f"[green]✓ Indexed {inserted} memories in {ingest_ms:.0f}ms[/green]\n")

    # Pre-compute BM25 and vector results for each query (constant across k/w combinations)
    console.print(
        "[cyan]⚡ Pre-computing baseline BM25 and Vector results for all 30 queries...[/cyan]"
    )
    bm25_results_cache: List[List[int]] = []
    vec_results_cache: List[List[int]] = []
    for q in queries:
        bm25_results_cache.append([r["id"] for r in search_bm25(conn, q["query"], limit=5)])
        vec_results_cache.append([r["id"] for r in search_vector(conn, q["query"], limit=5)])

    # ── Grid Sweep ─────────────────────────────────────────────────────────
    console.print("[cyan]⚙️  Running grid sweep across k and weight combinations...[/cyan]\n")
    grid_results: List[Dict[str, Any]] = []

    for k in K_VALUES:
        for text_w in TEXT_WEIGHTS:
            vec_w = round(1.0 - text_w, 2)
            combo_h1 = combo_h3 = combo_h5 = combo_rr = 0.0
            latencies: List[float] = []

            for q in queries:
                t_start = time.perf_counter()
                results = hybrid_search(
                    conn, q["query"], limit=5, k=k, text_weight=text_w, vec_weight=vec_w
                )
                latencies.append((time.perf_counter() - t_start) * 1000)

                expected_ids = _build_ground_truth_ids(corpus, q["expected_tags"])
                result_ids = [r["id"] for r in results]
                h1, h3, h5, rr = _score_results(result_ids, expected_ids)
                combo_h1 += h1
                combo_h3 += h3
                combo_h5 += h5
                combo_rr += rr

            n = len(queries)
            grid_results.append(
                {
                    "k": k,
                    "text_w": text_w,
                    "vec_w": vec_w,
                    "Hit@1": round(combo_h1 / n, 4),
                    "Hit@3": round(combo_h3 / n, 4),
                    "MRR": round(combo_rr / n, 4),
                    "p50_ms": round(statistics.median(latencies), 2),
                }
            )

    conn.close()
    cleanup()

    # ── Sort by MRR (primary), Hit@1 (secondary) ──────────────────────────
    grid_results.sort(key=lambda x: (x["MRR"], x["Hit@1"]), reverse=True)
    best = grid_results[0]

    # Also get baseline BM25 and Vector-only metrics for comparison
    bm25_h1 = bm25_h3 = bm25_rr = 0.0
    vec_h1 = vec_h3 = vec_rr = 0.0
    for q_idx, q in enumerate(queries):
        expected_ids = _build_ground_truth_ids(corpus, q["expected_tags"])
        bm_h1, bm_h3, _, bm_rr = _score_results(bm25_results_cache[q_idx], expected_ids)
        v_h1, v_h3, _, v_rr = _score_results(vec_results_cache[q_idx], expected_ids)
        bm25_h1 += bm_h1
        bm25_h3 += bm_h3
        bm25_rr += bm_rr
        vec_h1 += v_h1
        vec_h3 += v_h3
        vec_rr += v_rr

    n = len(queries)
    baselines = {
        "BM25 (FTS5)": {
            "Hit@1": round(bm25_h1 / n, 4),
            "Hit@3": round(bm25_h3 / n, 4),
            "MRR": round(bm25_rr / n, 4),
        },
        "Vector (sqlite-vec)": {
            "Hit@1": round(vec_h1 / n, 4),
            "Hit@3": round(vec_h3 / n, 4),
            "MRR": round(vec_rr / n, 4),
        },
    }

    # ── Render Results ─────────────────────────────────────────────────────
    # Top-10 leaderboard
    leaderboard = Table(
        title=f"🏆 Top-10 RRF Configurations (sorted by MRR) — {len(corpus)} Real Memories",
        header_style="bold magenta",
    )
    leaderboard.add_column("Rank", justify="right", style="dim")
    leaderboard.add_column("k", justify="center")
    leaderboard.add_column("text_w", justify="center")
    leaderboard.add_column("vec_w", justify="center")
    leaderboard.add_column("Hit@1", justify="center")
    leaderboard.add_column("Hit@3", justify="center")
    leaderboard.add_column("MRR", justify="center", style="bold yellow")
    leaderboard.add_column("p50 ms", justify="right")

    for rank_i, row in enumerate(grid_results[:10], 1):
        is_best = rank_i == 1
        color = "bold green" if is_best else "white"
        prefix = (
            "🥇 " if rank_i == 1 else ("🥈 " if rank_i == 2 else ("🥉 " if rank_i == 3 else ""))
        )
        leaderboard.add_row(
            f"[{color}]{prefix}{rank_i}[/{color}]",
            f"[{color}]{row['k']}[/{color}]",
            f"[{color}]{row['text_w']}[/{color}]",
            f"[{color}]{row['vec_w']}[/{color}]",
            f"[{color}]{row['Hit@1'] * 100:.1f}%[/{color}]",
            f"[{color}]{row['Hit@3'] * 100:.1f}%[/{color}]",
            f"[{color}]{row['MRR']:.4f}[/{color}]",
            f"{row['p50_ms']:.1f}ms",
        )

    console.print(leaderboard)
    console.print("")

    # Baseline comparison
    baseline_table = Table(
        title="📊 Baseline Comparison (All Methods on Real-World Corpus)", header_style="bold blue"
    )
    baseline_table.add_column("Method", style="bold", width=28)
    baseline_table.add_column("Hit@1", justify="center")
    baseline_table.add_column("Hit@3", justify="center")
    baseline_table.add_column("MRR", justify="center", style="bold yellow")
    baseline_table.add_column("k config", justify="center", style="dim")

    for method, stats in baselines.items():
        baseline_table.add_row(
            method,
            f"{stats['Hit@1'] * 100:.1f}%",
            f"{stats['Hit@3'] * 100:.1f}%",
            f"{stats['MRR']:.4f}",
            "N/A",
        )
    baseline_table.add_row(
        "[bold green]Battery Hybrid — BEST[/bold green]",
        f"[bold green]{best['Hit@1'] * 100:.1f}%[/bold green]",
        f"[bold green]{best['Hit@3'] * 100:.1f}%[/bold green]",
        f"[bold green]{best['MRR']:.4f}[/bold green]",
        f"[bold green]k={best['k']}, tw={best['text_w']}, vw={best['vec_w']}[/bold green]",
    )
    console.print(baseline_table)

    console.print(
        f"\n[bold green]✅ Optimal configuration found:[/bold green] "
        f"[cyan]k={best['k']}[/cyan], text_weight={best['text_w']}, vec_weight={best['vec_w']} "
        f"→ MRR={best['MRR']:.4f}, Hit@1={best['Hit@1'] * 100:.1f}%, Hit@3={best['Hit@3'] * 100:.1f}%"
    )

    if best["k"] != 60:
        console.print(
            f"[yellow]💡 Note: k={best['k']} beats the academic default k=60. "
            f"Lower k provides more rank-position signal for short, factual memory assertions.[/yellow]"
        )

    # ── Markdown Report ────────────────────────────────────────────────────
    if output_markdown:
        md = f"""# ⚙️ Battery RRF Parameter Tuning Report

**Evaluation Corpus:** {len(corpus)} real-world engineering memories (Battery ADRs, README, docstrings, curated rules)\\
**Evaluation Queries:** {len(queries)} authentic developer and LLM agent queries\\
**Grid Sweep:** {len(K_VALUES)} k values × {len(TEXT_WEIGHTS)} weight combinations = {len(K_VALUES) * len(TEXT_WEIGHTS)} combinations tested

---

## Optimal Configuration Found

| Parameter | Default (k=60) | **Optimal (tuned)** |
| :--- | :---: | :---: |
| **k (RRF smoothing constant)** | 60 | **{best["k"]}** |
| **text_weight (BM25)** | 0.5 | **{best["text_w"]}** |
| **vec_weight (Vector)** | 0.5 | **{best["vec_w"]}** |
| **Hit@1** | — | **{best["Hit@1"] * 100:.1f}%** |
| **Hit@3** | — | **{best["Hit@3"] * 100:.1f}%** |
| **MRR** | — | **{best["MRR"]:.4f}** |

---

## Top-10 RRF Configurations (by MRR)

| Rank | k | text_w | vec_w | Hit@1 | Hit@3 | MRR | p50 ms |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
"""
        for rank_i, row in enumerate(grid_results[:10], 1):
            best_marker = " ⭐" if rank_i == 1 else ""
            md += (
                f"| {rank_i}{best_marker} | {row['k']} | {row['text_w']} | {row['vec_w']} "
                f"| {row['Hit@1'] * 100:.1f}% | {row['Hit@3'] * 100:.1f}% "
                f"| {row['MRR']:.4f} | {row['p50_ms']:.1f}ms |\n"
            )

        md += f"""
---

## Baseline Comparison

| Method | Hit@1 | Hit@3 | MRR |
| :--- | :---: | :---: | :---: |
| BM25 (FTS5) | {baselines["BM25 (FTS5)"]["Hit@1"] * 100:.1f}% | {baselines["BM25 (FTS5)"]["Hit@3"] * 100:.1f}% | {baselines["BM25 (FTS5)"]["MRR"]:.4f} |
| Vector (sqlite-vec) | {baselines["Vector (sqlite-vec)"]["Hit@1"] * 100:.1f}% | {baselines["Vector (sqlite-vec)"]["Hit@3"] * 100:.1f}% | {baselines["Vector (sqlite-vec)"]["MRR"]:.4f} |
| **Battery Hybrid (k={best["k"]}, tw={best["text_w"]})** | **{best["Hit@1"] * 100:.1f}%** | **{best["Hit@3"] * 100:.1f}%** | **{best["MRR"]:.4f}** |
"""
        TUNER_REPORT_PATH.write_text(md, encoding="utf-8")
        console.print(f"\n[dim]Tuning report saved to {TUNER_REPORT_PATH}[/dim]")

    return {
        "best": best,
        "all_results": grid_results,
        "baselines": baselines,
        "corpus_size": len(corpus),
        "query_count": len(queries),
    }


if __name__ == "__main__":
    run_rrf_tuner()
