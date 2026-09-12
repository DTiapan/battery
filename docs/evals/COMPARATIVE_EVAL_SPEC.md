# Comparative Evaluation Spec — Battery vs memex vs local-memory-mcp

> **Status:** Approved spec v2 (G2 gate) — **execute once, publish report, stop.**  
> **Owner:** Battery maintainers  
> **Last updated:** 2026-09-12  
> **Roadmap gate:** [PRODUCT_ROADMAP §8 G2](../roadmap/PRODUCT_ROADMAP.md#8-research--external-impact-long-term-goal)

---

## 1. Objective

Produce **reproducible, publishable proof** that Battery retrieval is competitive before any market launch — using a **neutral public benchmark first**, not side-by-side README numbers.

### What we are proving

| Tier | Question | Dataset |
|------|----------|---------|
| **Tier 1 (primary)** | Does Battery beat or match open local MCP memory servers on a **shared, third-party** dev-memory benchmark? | [Sediment benchmark](https://github.com/rendro/sediment-benchmark) |
| **Tier 2 (supplementary)** | How does Battery perform on **real engineering agent memory** (ADRs, rules, decisions)? | Battery real-world harness (92 / 30) |

### What we are NOT doing

- ❌ Comparing Battery’s published MRR to memex’s or mnemon’s published MRR (different corpora, metrics, embeddings — **invalid**)
- ❌ Claiming “best memory system” without running the same queries on the same data
- ❌ Building new engine features after the frozen report merges

**Success = one frozen report** (`src/battery/evals/comparative_benchmark_report.md`) with Tier 1 complete and Tier 2 optional.

**Stop rule:** Report merged → scorecard G2 updated → **no further engine work** until user interviews (Path A).

---

## 2. Why neutral dataset first?

Competitors do not ship portable golden sets:

| System | Published retrieval benchmark? |
|--------|-------------------------------|
| [memex](https://github.com/kioie/memex) | No — scale tests only (1k–5k rows) |
| [local-memory-mcp](https://github.com/madetocreate/local-memory-mcp) | No public eval doc |
| [mnemon-memory-mcp](https://github.com/nikitacometa/mnemon-memory-mcp) | Yes — but **private** 797-memory corpus; not reproducible |

**Sediment benchmark** is the right neutral anchor:

- **1,000** synthetic developer memories, **200** queries, 6 categories
- Public JSONL in repo — no API key to run
- Existing harness: `MemoryAdapter` ABC, shared metrics (Recall@k, MRR, nDCG@5)
- Designed for MCP / agent memory systems (architecture, code patterns, troubleshooting, etc.)
- Optional phases: temporal, dedup, latency (run retrieval first for launch gate)

Battery’s RW corpus remains valuable as **Tier 2** — it tests our wedge (ADR/rule memory), but **Tier 1 is required** for honest competitor claims.

---

## 3. Systems under test

| ID | System | Repo | Role | Retrieval config |
|----|--------|------|------|------------------|
| **B0** | Battery hybrid | this repo | **Subject** | Adaptive RRF (`hybrid_search`, `verify=False`) |
| **B1** | Battery BM25 | this repo | Ablation | FTS5 only |
| **B2** | Battery vector | this repo | Ablation | sqlite-vec only |
| **C1** | memex | [kioie/memex](https://github.com/kioie/memex) | Competitor | Default keyword (`recall` / `retrieve_context`) |
| **C1b** | memex hybrid | same | Competitor variant | `MEMEX_HYBRID=1` (local vectors + RRF) |
| **C2** | local-memory-mcp | [@studiomeyer/local-memory-mcp](https://github.com/madetocreate/local-memory-mcp) | Competitor | `memory_search` (FTS5) |
| **R0** | ChromaDB | Sediment harness baseline | Reference only | Default Sediment `chromadb_baseline.py` |

**Pin all versions** in the report header (Battery git tag, memex release, npm package version, sediment-benchmark commit SHA).

### Out of scope

- Hosted memory (Mem0, Zep) — different trust model; Sediment already includes Mem0 if we extend later
- Code-indexing (Context Fabric, Engram-MCP)
- Agent end-to-end task success — G3 / LongMemEval
- Hooks, handoff, rot — proven separately (Sprint C); not retrieval comparison

---

## 4. Tier 1 — Sediment benchmark (primary)

### 4.1 Dataset (upstream, do not modify)

Source: `https://github.com/rendro/sediment-benchmark` → `dataset/`

| File | Contents |
|------|----------|
| `memories.jsonl` | 1,000 memories — `id`, `content`, `category`, `scope`, `tags` |
| `queries.jsonl` | 200 queries — `id`, `query`, `expected` (memory IDs), `category`, `difficulty` |
| `temporal.jsonl` | 50 update sequences (Phase 2 optional) |

**Categories:** architecture (200), code_patterns (200), project_facts (200), user_preferences (150), troubleshooting (150), cross_project (100)

**Difficulty:** 50 easy, 100 medium, 50 hard

### 4.2 Harness strategy

**Do not reimplement metrics.** Extend the Sediment harness:

```text
battery/
  vendor/sediment-benchmark/     # git submodule or pinned clone
    dataset/                     # use upstream JSONL as-is
    metrics/                     # reuse retrieval.py (MRR, Recall@k, nDCG@5)
    adapters/
      battery.py                 # NEW — implements MemoryAdapter
      memex.py                   # NEW
      local_memory_mcp.py        # NEW
```

Alternative (acceptable): copy `dataset/*.jsonl` + `metrics/retrieval.py` into `src/battery/evals/sediment/` with LICENSE attribution — submodule preferred for reproducibility.

### 4.3 Adapter contract (from Sediment)

```python
class MemoryAdapter(ABC):
    name: str

    async def setup(self) -> None: ...
    async def teardown(self) -> None: ...
    async def reset(self) -> None: ...
    async def store(self, item: MemoryItem) -> None: ...
    async def recall(self, query: str, limit: int = 5) -> list[RecallResult]: ...
    async def count(self) -> int: ...
```

`RecallResult` must include stable `memory_id` matching Sediment `expected` IDs — map Battery insert IDs ↔ Sediment `mem_XXXX` at ingest time.

### 4.4 Battery adapter (B0–B3)

- `store`: `insert_memory` with Sediment `content`, `category` mapped to Battery categories
- `recall`: return top-5 by `hybrid_search` (B0), `search_bm25` (B1), or `search_vector` (B2)
- Fresh SQLite DB per run under `evals/.comparative_workspaces/battery-sediment/`
- **Disable JIT verify** on recall (`verify=False`) — rot is a separate eval

### 4.5 memex adapter (C1 / C1b)

- MCP subprocess: `remember` per memory, `recall` / `retrieve_context` for query
- Isolated `MEMEX_DIR` per run
- C1b: `MEMEX_HYBRID=1` — separate report row

### 4.6 local-memory-mcp adapter (C2)

- `npx @studiomeyer/local-memory-mcp` with isolated `MEMORY_DB_PATH`
- Ingest via `memory_learn` / category-appropriate tools; search via `memory_search`

### 4.7 Tier 1 phases for launch

| Phase | Required for G2? | Metrics |
|-------|------------------|---------|
| **Retrieval** | ✅ **Yes** | Recall@1/3/5/10, MRR, nDCG@5 — by category + difficulty |
| Temporal | Optional | Recency@1/3, temporal MRR |
| Dedup | Optional | Consolidation rate, post-dedup recall |
| Latency | Recommended | Store/recall p50, p95, p99 |

**Launch gate uses retrieval phase only.**

### 4.8 Tier 1 launch gates

| Gate | Condition |
|------|-----------|
| **G2a** | B0 MRR ≥ max(C1, C2) on Sediment retrieval, **or** within **0.01** MRR with lower p95 recall latency |
| **G2b** | B0 Recall@5 ≥ ChromaDB baseline (R0) on same run — proves hybrid beats naive vector-only |
| **G2c** | Zero ingest failures across 1,000 memories (or documented exclusions → run INVALID) |
| **G2d** | Report includes MRR sliced by `difficulty` and `category` — document where Battery loses |

### 4.9 Tier 1 run command

```bash
# After adapters land in vendor/sediment-benchmark/
cd vendor/sediment-benchmark
python run.py --systems battery,memex,local-memory-mcp,chromadb \
              --phases retrieval,latency \
              --seed 42
python report.py
# Copy results/report.md → src/battery/evals/comparative_benchmark_report.md
```

Or via Battery CLI wrapper (Phase 2):

```bash
uv run battery eval --comparative --tier sediment --systems battery,memex,local-memory-mcp
```

---

## 5. Tier 2 — Battery real-world (supplementary)

Answers: *“How does Battery perform on genuine ADR/README engineering memory?”*

| Suite | Corpus | Queries | Source |
|-------|--------|---------|--------|
| **RW** | 92 memories | 30 queries | `get_realworld_dataset()` |
| **S500** | 500 memories | 30 queries | `get_stress_dataset(500)` — optional scale slice |

### Ground truth

- `ground_truth_tag` per memory; `expected_tags` per query (existing harness)
- **Same fairness rules:** cold start, identical text, k=5, local embeddings only

### Tier 2 purpose

- Regression guard for Battery’s product niche
- **Secondary row** in comparative report — not sufficient alone for “we beat memex”
- If Tier 1 and Tier 2 disagree, **Tier 1 wins** for launch positioning

### Tier 2 run (after Tier 1 adapters exist)

Reuse Sediment adapters’ `store`/`recall` against exported corpus:

```bash
uv run battery eval --comparative --tier battery-rw --systems battery,memex,local-memory-mcp
uv run battery eval --comparative --tier battery-s500 --systems battery,memex,local-memory-mcp
```

Export format unchanged from v1 spec (`comparative_corpus_realworld.json`).

---

## 6. Metrics (shared definitions)

Use **Sediment `metrics/retrieval.py`** for Tier 1. For Tier 2, align with same definitions:

| Metric | Definition |
|--------|------------|
| **MRR** | Mean reciprocal rank of first expected hit in top-k |
| **Recall@k** | Fraction of queries with ≥1 expected ID in top-k |
| **nDCG@5** | Normalized discounted cumulative gain (Tier 1 only) |
| **Hit@0** | Queries with zero relevant hit in top-5 |
| **p50 / p95 latency** | Wall-clock per `recall` call (ms), excluding bulk ingest |

Do not mix Sediment MRR with Battery harness MRR in one table without labeling the suite.

---

## 7. Fairness rules (all tiers)

1. **Cold start** — `reset()` → ingest full corpus → query
2. **Same bytes** — identical `content` strings from dataset file
3. **Best honest config** — each system’s recommended retrieval mode per upstream README
4. **k = 5** for cross-system comparison tables (Sediment also reports k=10 internally)
5. **Local only** — no cloud embedding APIs; memex hybrid must use documented local path
6. **Hardware block** in report — CPU, RAM, OS, Python/Go/Node versions
7. **No cherry-picking** — Tier 1 full 200 queries required; cannot subset to “wins only”

---

## 8. Execution plan

### Phase 1 — Sediment integration (1 PR) ✅

| Task | Output | Status |
|------|--------|--------|
| Add `vendor/sediment-benchmark` submodule @ pinned SHA | [SEDIMENT_PIN.md](./SEDIMENT_PIN.md) | ✅ |
| `src/battery/evals/sediment/battery_adapter.py` | B0, B1, B2 `MemoryAdapter` | ✅ |
| `src/battery/evals/sediment/runner.py` + CLI | `uv run battery eval --comparative` | ✅ |
| Smoke test (1k/200 retrieval) | MRR **0.609**, Recall@5 **0.790** (2026-09-12) | ✅ |

### Phase 2 — Competitor adapters (1 PR)

| Task | Output |
|------|--------|
| `adapters/memex.py`, `adapters/local_memory_mcp.py` | C1, C1b, C2 |
| `docs/evals/COMPARATIVE_SETUP.md` | Install pins |
| `battery eval --comparative` CLI wrapper | Delegates to sediment `run.py` |

### Phase 3 — Full run & freeze (1 PR, then stop)

```bash
# Tier 1 — required
cd vendor/sediment-benchmark && python run.py --systems battery,memex,local-memory-mcp,chromadb --phases retrieval,latency --seed 42

# Tier 2 — supplementary
uv run battery eval --comparative --tier battery-rw --systems battery,memex,local-memory-mcp
```

| Deliverable | Path |
|-------------|------|
| Frozen report | `src/battery/evals/comparative_benchmark_report.md` |
| Raw JSON | `src/battery/evals/comparative_benchmark_results.json` |
| Scorecard G2 | pass/fail on G2a–G2d |
| README | Link under “Retrieval benchmarks” |

---

## 9. Report template

```markdown
# Comparative Retrieval Benchmark — Battery vs memex vs local-memory-mcp

**Run date:** YYYY-MM-DD  
**Harness:** sediment-benchmark @ <sha>  
**Battery:** v0.5.0 @ <sha>  
**memex:** vX.Y.Z | **local-memory-mcp:** @x.y.z  
**Machine:** <CPU> / <RAM> / <OS>

## Tier 1 — Sediment (1,000 memories, 200 queries) [PRIMARY]

| System | MRR | Recall@5 | nDCG@5 | Recall@1 | p95 recall ms |
|--------|----:|---------:|-------:|---------:|--------------:|
| Battery hybrid (B0) | | | | | |
| memex keyword (C1) | | | | | |
| memex hybrid (C1b) | | | | | |
| local-memory-mcp (C2) | | | | | |
| ChromaDB baseline (R0) | | | | | |

### By difficulty (MRR)

| easy (50) | medium (100) | hard (50) |
|-----------|--------------|-----------|

### By category (MRR)

| architecture | code_patterns | project_facts | user_preferences | troubleshooting | cross_project |

## Tier 2 — Battery real-world (92 / 30) [SUPPLEMENTARY]

| System | MRR | Hit@1 | Hit@0 | p95 ms |
|--------|----:|------:|------:|-------:|

## Launch gate verdict

- [ ] G2a: B0 MRR ≥ max(C1, C2) OR within 0.01 @ lower p95
- [ ] G2b: B0 Recall@5 ≥ R0 (ChromaDB)
- [ ] G2c: 0 ingest failures
- [ ] G2d: Losses documented by category/difficulty

## Honest limitations

- Sediment corpus is synthetic; Tier 2 is small (n=30)
- ...
```

---

## 10. Launch positioning

### Allowed after Tier 1 passes

> “On the open [Sediment developer-memory benchmark](https://github.com/rendro/sediment-benchmark) (1,000 memories, 200 queries), Battery hybrid retrieval achieved MRR **X.XX** vs memex **X.XX** and local-memory-mcp **X.XX** under a shared harness ([report](…)).”

### Allowed after Tier 2 (additive, not substitute)

> “On Battery’s open real-world engineering corpus (92 memories, 30 queries), hybrid MRR is **0.91** ([realworld report](…)).”

### Never allowed

- Comparing our Tier 2 score to mnemon’s published 0.878 (different dataset)
- “Best memory system” without Tier 1
- Claiming novelty of hybrid RRF (prior art exists)

---

## 11. Reference — Battery-only baselines (Tier 2, not competitor proof)

From internal harness (2026-09-12):

**Real-world (92 / 30):**

| Mode | Hit@1 | MRR | p50 ms |
|------|------:|----:|-------:|
| Hybrid (B0) | 86.7% | 0.9083 | 25.3 |

**Stress-500:**

| Mode | Hit@1 | MRR | p50 ms |
|------|------:|----:|-------:|
| Hybrid (B0) | 83.3% | 0.8594 | 13.4 |

These numbers are **regression baselines** until Tier 1 competitor run completes.

---

## 12. Risks & mitigations

| Risk | Mitigation |
|------|------------|
| Sediment adapter maintenance | Pin submodule SHA; upstream PR to add `battery` adapter |
| memex MCP ingest slow | Report ingest latency separately; same total corpus |
| ID mapping bugs | Unit test: store `mem_0001` → recall returns same ID |
| Synthetic ≠ real dev memory | Tier 2 RW corpus as supplement |
| We only run Tier 2 | **G2 FAIL** — Tier 1 required for launch claims |

---

## 13. Checklist — done means stop

- [ ] Spec v2 merged
- [ ] sediment-benchmark submodule + Battery adapter
- [ ] memex + local-memory-mcp adapters
- [ ] Tier 1 full run (200 queries, all systems)
- [ ] Tier 2 RW run (optional but recommended)
- [ ] `comparative_benchmark_report.md` merged
- [ ] Scorecard G2 pass/fail
- [ ] README updated
- [ ] **Stop** — interviews next, not engine work

---

## Document history

| Version | Date | Changes |
|---------|------|---------|
| v1 | 2026-09-12 | Initial: Battery RW + S500 as primary |
| v2 | 2026-09-12 | **Rewrite:** Sediment Tier 1 (neutral public benchmark); Battery RW Tier 2 (supplementary); invalid to compare published scores across vendors |
