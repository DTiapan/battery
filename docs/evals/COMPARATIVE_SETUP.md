# Comparative Eval — Environment Setup

Companion to [COMPARATIVE_EVAL_SPEC.md](./COMPARATIVE_EVAL_SPEC.md) (v2).  
**Frozen results:** [BENCHMARK_RESULTS.md](./BENCHMARK_RESULTS.md) · [comparative_benchmark_report.md](../../src/battery/evals/comparative_benchmark_report.md)

## Quick install (recommended)

```bash
bash scripts/install-benchmark-deps.sh
export PATH="$(go env GOPATH)/bin:${HOME}/.local/bin:$PATH"
```

## Overview

| Tier | Harness | Dataset location |
|------|---------|------------------|
| **1 (primary)** | [sediment-benchmark](https://github.com/rendro/sediment-benchmark) | `vendor/sediment-benchmark/dataset/*.jsonl` |
| **2 (supplementary)** | Battery `eval --comparative` | `get_realworld_dataset()` / stress-500 |

## Prerequisites

- Python 3.11+ (`uv sync` for Battery)
- Go 1.22+ (memex)
- Node 20+ with `npx` (local-memory-mcp)
- ~500 MB disk (ONNX model + temp DBs)

## 1. Sediment benchmark (Tier 1)

```bash
cd /path/to/battery

# Submodule (preferred — pin SHA in report)
git submodule add https://github.com/rendro/sediment-benchmark.git vendor/sediment-benchmark
cd vendor/sediment-benchmark
git checkout <pinned-sha>   # record in comparative report

python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Sanity: ChromaDB baseline only
python run.py --systems chromadb --phases retrieval --seed 42

# Full Tier 1 comparative (recommended)
uv run battery eval --comparative \
  --systems battery,memex,local-memory-mcp \
  --phases retrieval \
  --write-report
```

Dataset files (no API key):

- `dataset/memories.jsonl` — 1,000 memories
- `dataset/queries.jsonl` — 200 queries with `expected` memory IDs
- `dataset/temporal.jsonl` — optional temporal phase

## 2. Battery (Tier 1 adapter)

Adapter lives at `vendor/sediment-benchmark/adapters/battery.py` (to be implemented).

Isolated DB per run:

```bash
export BATTERY_COMPARATIVE_DB="$(pwd)/src/battery/evals/.comparative_workspaces/battery-sediment/battery.db"
mkdir -p "$(dirname "$BATTERY_COMPARATIVE_DB")"
```

Sanity before comparative:

```bash
uv run battery eval --real
```

## 3. memex (Tier 1 competitor)

Requires **Go 1.22+** on PATH.

```bash
go install github.com/kioie/memex/cmd/memex@v0.6.0   # pin version in report
export PATH="$PATH:$(go env GOPATH)/bin"
memex version

# Run (C1 keyword)
uv run battery eval --comparative --systems battery,memex,local-memory-mcp --phases retrieval --write-report

# C1b hybrid variant (separate run)
MEMEX_HYBRID=1 uv run battery eval --comparative --systems memex-hybrid --phases retrieval
```

Data dir is set automatically per run under `.comparative_workspaces/memex/`.

## 4. local-memory-mcp (Tier 1 competitor)

```bash
npx @studiomeyer/local-memory-mcp --version   # pin in report

export MEMORY_DB_PATH="$(pwd)/src/battery/evals/.comparative_workspaces/local-memory-sediment/memory.db"
mkdir -p "$(dirname "$MEMORY_DB_PATH")"
```

## 5. Tier 2 — Battery real-world (supplementary)

After Tier 1 adapters work:

```bash
uv run battery eval --comparative --tier battery-rw --systems battery,memex,local-memory-mcp
uv run battery eval --comparative --tier battery-s500 --systems battery,memex,local-memory-mcp
```

## Workspace layout

```text
battery/
  vendor/sediment-benchmark/          # submodule @ pinned SHA (see SEDIMENT_PIN.md)
    dataset/memories.jsonl
    dataset/queries.jsonl
  src/battery/evals/sediment/
    battery_adapter.py                # Battery MemoryAdapter (B0–B2)
    runner.py                         # registers + delegates to Sediment run.py
    adapters/memex.py                 # Phase 2
    adapters/local_memory_mcp.py      # Phase 2
  src/battery/evals/
    .comparative_workspaces/          # gitignored
    comparative_benchmark_report.md   # frozen output
    comparative_benchmark_results.json
```

### `.gitignore` additions

```gitignore
src/battery/evals/.comparative_workspaces/
vendor/sediment-benchmark/.venv/
vendor/sediment-benchmark/results/raw/
```

## Reference machine

Document in report header:

- CPU model, core count
- RAM
- OS version
- Python / Go / Node versions
- `uname -a` or `system_profiler SPHardwareDataType`

## Battery CLI (Phase 1 — implemented)

```bash
# Tier 1 smoke / full run (Battery hybrid on Sediment 1k/200)
uv run battery eval --comparative --tier sediment --systems battery --phases retrieval

# Ablation modes
uv run battery eval --comparative --systems battery,battery-bm25,battery-vector --phases retrieval

# ChromaDB baseline (requires: pip install -e vendor/sediment-benchmark)
uv run battery eval --comparative --systems battery,chromadb --phases retrieval
```

Submodule pin: [SEDIMENT_PIN.md](./SEDIMENT_PIN.md)
