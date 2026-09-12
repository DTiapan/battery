# Battery Benchmark Results — v0.5.0

> **Frozen:** 2026-09-12 · **Harness:** [Sediment benchmark](https://github.com/rendro/sediment-benchmark) @ `49ab23a`  
> **Full report:** [`comparative_benchmark_report.md`](../../src/battery/evals/comparative_benchmark_report.md)  
> **Spec:** [COMPARATIVE_EVAL_SPEC.md](./COMPARATIVE_EVAL_SPEC.md)

---

## Headline

On the **public Sediment dev-memory benchmark** (1,000 synthetic developer memories, 200 queries, seed 42), **Battery hybrid retrieval outperformed both open MCP memory competitors** we tested:

| System | MRR | Recall@5 | Recall@1 |
|--------|----:|---------:|---------:|
| **Battery (hybrid RRF)** | **0.609** | **0.790** | 0.470 |
| ChromaDB (vector baseline) | 0.611 | 0.785 | 0.475 |
| memex v0.6.0 | 0.512 | 0.635 | 0.425 |
| local-memory-mcp 1.0.7 | 0.457 | 0.600 | 0.365 |
| memex-hybrid | 0.423 | 0.580 | 0.315 |

**Launch gates G2a–G2d:** all passed. See [scorecard](../metrics/IMPROVEMENT_SCORECARD.md).

---

## What this proves (and what it doesn't)

### Proves

- Battery beats **memex** and **local-memory-mcp** on the same neutral public corpus with the same metrics harness.
- Hybrid search (BM25 + vector + adaptive RRF) beats naive vector-only on **Recall@5** (G2b).
- Results are **reproducible** — submodule-pinned dataset, CLI command, version pins in report header.

### Does not prove

- "Best memory system in the world" — ChromaDB MRR is statistically tied (0.611 vs 0.609).
- Real-world agent task success — Sediment is synthetic dev-memory, not live coding sessions.
- Tier 2 (Battery's own 92-memory ADR corpus) was not part of this frozen report.

---

## Where Battery is strongest / weakest (G2d)

| Slice | Battery MRR |
|-------|------------:|
| **Best category:** code_patterns | 0.713 |
| **Worst category:** cross_project | 0.472 |
| **Best difficulty:** easy | 0.886 |
| **Worst difficulty:** hard | 0.382 |

Hard and cross-project queries are the known improvement areas.

---

## Real-world eval (separate harness)

Battery's own engineering-memory corpus (`battery eval --real`, 92 memories / 30 queries):

| Strategy | Hit@1 | MRR |
|----------|------:|----:|
| BM25 | 80.0% | 0.86 |
| Vector | 83.3% | 0.89 |
| **Hybrid** | **86.7%** | **0.91** |

Report: [`realworld_benchmark_report.md`](../../src/battery/evals/realworld_benchmark_report.md)

---

## Reproduce Tier 1 comparative

```bash
git clone https://github.com/DTiapan/battery.git
cd battery
git submodule update --init vendor/sediment-benchmark

# Install Go, memex, Node, ChromaDB
bash scripts/install-benchmark-deps.sh
export PATH="$(go env GOPATH)/bin:${HOME}/.local/bin:$PATH"

# Full run (~25 min with ChromaDB embedding)
uv run battery eval --comparative \
  --systems battery,chromadb,memex,memex-hybrid,local-memory-mcp \
  --phases retrieval \
  --write-report
```

Output: `src/battery/evals/comparative_benchmark_report.md`

Setup details: [COMPARATIVE_SETUP.md](./COMPARATIVE_SETUP.md)

---

## Environment (reference machine)

| Component | Version |
|-----------|---------|
| Battery | 0.5.0 |
| Python | 3.11.7 |
| memex | 0.6.0 |
| local-memory-mcp | @studiomeyer/local-memory-mcp@1.0.7 |
| Node | v26.8.1 |
| Go | 1.27.1 |
| Host | Darwin arm64 |
| Sediment SHA | `49ab23a245564111f9cc147fbb8e82885ffad7d6` |

---

## Caveats for publication

1. **ChromaDB** had 6 ONNX store errors (994/1000 stored) on the reference machine — treat as indicative.
2. **Battery** skipped 2 memories via content-hash dedup (998/1000) — documented, queries unaffected.
3. **Latency:** memex and local-memory-mcp are faster at recall p95 (~2–7 ms vs Battery ~15 ms).
4. **Single-machine run** — reproducible via CLI, not multi-host validated.

---

## Suggested LinkedIn post (copy-paste starter)

> Most local AI memory tools for coding agents can't prove retrieval quality — they ship scale tests or private corpora.
>
> I built **Battery** — local hybrid memory (BM25 + vectors + RRF) as an MCP server for Cursor and Claude Code — and ran it through the **public Sediment benchmark**: 1,000 dev memories, 200 queries, same harness as memex and local-memory-mcp.
>
> Results (MRR / Recall@5):
> • Battery: **0.609 / 0.790**
> • memex: 0.512 / 0.635
> • local-memory-mcp: 0.457 / 0.600
>
> No cloud APIs. Single SQLite file. Git-committable BATTERY.md mirror.
>
> Open source (MIT): github.com/DTiapan/battery
> Full reproducible report in the repo.

Adjust tone to your voice. Link the repo and optionally the report path.
