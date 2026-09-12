# Battery

**Local AI memory for coding agents** — an MCP server with hybrid search, session capture, and a git-committable `BATTERY.md` mirror.

> **Portable project context for Cursor, Claude Code, Claude Desktop, and any MCP client.**  
> Store architectural decisions and rules on your machine. Recall them with BM25 + vector search. Sync a human-readable mirror to git. No cloud embedding APIs. No external database daemons.

[![CI](https://github.com/DTiapan/battery/actions/workflows/ci.yml/badge.svg)](https://github.com/DTiapan/battery/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python: 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue.svg)](https://www.python.org/)
[![MCP: 2.x](https://img.shields.io/badge/MCP-2.x%20Compliant-green.svg)](https://modelcontextprotocol.io/)
[![Version: 0.5.0](https://img.shields.io/badge/version-0.5.0-blue.svg)](pyproject.toml)

**Keywords:** local AI memory · MCP memory server · Cursor context · Claude Code memory · hybrid RAG · coding agent context · stale memory pruning · session checkpoints

---

## What is Battery?

Battery is a **local-first memory engine** for AI-assisted software development. It gives your coding agents durable project context — rules, decisions, preferences, and session summaries — that survives tool switches and new sessions.

Think of the LLM as the motor and your project context as the **battery pack**: swap tools without re-explaining everything from scratch.

| You get | How |
|--------|-----|
| Semantic + keyword recall | Hybrid BM25 (FTS5) + dense vectors fused with RRF |
| Human-readable audit trail | Auto-synced `BATTERY.md` you can commit to git |
| Polyglot tool support | MCP tools, resources, and prompts for any MCP client |
| Session lifecycle capture | Claude Code hooks on session end and pre-compaction |
| Context rot protection | JIT citation verify on recall + `battery prune` for stale paths |
| Per-project isolation | Named context profiles (`battery profile create`) |

Storage is a single SQLite file (`battery.db`) with WAL mode, FTS5, and [`sqlite-vec`](https://github.com/asg017/sqlite-vec). Embeddings run locally via ONNX (`all-MiniLM-L6-v2`, ~12ms on CPU).

---

## The problem

Developers using multiple AI tools hit the same walls:

1. **Session amnesia** — every new chat re-explains stack choices, conventions, and constraints.
2. **Context silos** — Cursor doesn't know what Claude decided an hour ago.
3. **Static file rot** — `CLAUDE.md` and `.cursorrules` drift, can't be searched semantically, and bloat every prompt.
4. **Cloud memory lock-in** — hosted memory services store proprietary context on third-party servers.

Battery keeps memory **on your machine**, searchable, versionable, and pluggable into any MCP-native agent.

---

## Quick start

### Install

```bash
git clone https://github.com/DTiapan/battery.git
cd battery
uv sync
```

Requires **Python 3.11+** and [`uv`](https://github.com/astral-sh/uv).

### Initialize in your project

```bash
cd /path/to/your/project
uv run battery onboard
```

One command: creates `battery.db`, seeds starter memories, registers MCP in Cursor/Claude, and runs adoption checks.

Or step by step:

```bash
uv run battery init
```

### Save and recall context

```bash
# Save memories by category
uv run battery add "Use SQLite WAL + sqlite-vec for hybrid storage" -c decision
uv run battery add "All Python functions need type hints" -c rule

# Hybrid search (BM25 + vector + RRF)
uv run battery query "python typing guidelines"
```

### Connect to Cursor or Claude Desktop

```bash
uv run battery setup --client all
# or: --client cursor | --client claude
```

Then use MCP tools in chat: `recall_memory`, `save_memory`, `list_memories`, `forget_memory`.

### Auto-capture sessions (Claude Code)

```bash
uv run battery hook install --scope project
uv run battery doctor --adoption
```

Hooks fire on **SessionEnd** and **PreCompact**, writing episodic checkpoints you can inspect:

```bash
uv run battery checkpoint list
uv run battery checkpoint show --latest
```

Capture landed work on every git commit:

```bash
uv run battery git install
uv run battery git capture   # manual capture of HEAD commit
```

Prune memories that reference deleted files:

```bash
uv run battery prune --dry-run
uv run battery prune
```

### Hand off context between tools

Before switching from Cursor to Claude Code (or vice versa):

```bash
uv run battery handoff export --from-client cursor --to-client claude-code
# In the other tool:
uv run battery handoff load --latest
# Optional: persist loaded handoff as episodic memory
uv run battery handoff load --latest --ingest --to-client claude-code
```

Artifacts are written to `.battery/handoff/` in your project. Claude Code `SessionStart` hooks auto-inject the latest handoff when present.

### Move memory to another computer

**Team / project context** — commit `BATTERY.md` to git; on the new machine clone and run `battery sync`.

**Personal profile** — export a checksum-verified bundle:

```bash
battery profile export --profile default --out ~/battery-backup.battery-bundle --include-md
# On new machine after installing Battery:
battery profile import ~/battery-backup.battery-bundle --profile default --force
battery profile inspect ~/battery-backup.battery-bundle   # view manifest only
```

Bundles contain `battery.db` (+ optional `BATTERY.md`). ONNX model weights (~90MB) are **not** included — they re-download on first embed.

---

## Features (v0.2)

- **Hybrid retrieval** — BM25 + vector cosine similarity, fused with tuned RRF (k=5)
- **Living mirror** — bidirectional sync between SQLite and `BATTERY.md`
- **MCP server** — tools, `battery://context` / `battery://rules` resources, `battery-context` prompt
- **Context profiles** — isolate memory per repo or domain
- **Session checkpoints** — Claude Code lifecycle hooks + `battery checkpoint`
- **Git commit capture** — `battery git install` post-commit hook → episodic memory with `commit_sha`
- **Profile portability** — `battery profile export/import` checksum-verified bundles
- **Stale invalidation** — citation verify on recall + `battery prune`
- **Near-duplicate merge** — semantic dedup on save (cosine ≥ 0.88 → merge, returns `similarTo`)
- **Health checks** — `battery doctor` for DB, mirror sync, MCP, and hook adoption
- **Eval harness** — `battery eval` with real-world and stress-test corpora

---

## Connect to AI assistants

### Automated setup

```bash
uv run battery setup --client all
```

### Manual MCP config (Claude Desktop)

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "battery": {
      "command": "battery",
      "args": ["serve"]
    }
  }
}
```

### Cursor

Settings → Features → MCP → Add server: command `battery serve`.

### Profile-scoped server

```bash
uv run battery profile create payments-service
uv run battery use payments-service
uv run battery serve --profile payments-service
```

### MCP surface

| Tool | Purpose |
|------|---------|
| `recall_memory(query, limit, category)` | Hybrid search before answering |
| `save_memory(content, category, importance, file_paths?)` | Persist rules, decisions, citations |
| `list_memories(category, limit)` | Browse stored context |
| `forget_memory(memory_id)` | Tombstone stale entries |

| Resource | Purpose |
|----------|---------|
| `battery://context` | Active rules, decisions, preferences |
| `battery://rules` | Constraints and architectural rules only |

| Prompt | Purpose |
|--------|---------|
| `battery-context` | Inject task-relevant memory at session start |

---

## CLI reference

| Command | Description |
|---------|-------------|
| `battery init` | Create DB + `BATTERY.md` in current project |
| `battery onboard` | Init + seed + MCP setup + adoption doctor |
| `battery add "..." -c rule\|decision\|preference` | Save a memory |
| `battery query "..."` | Hybrid search with scored results |
| `battery list` | Show active memories |
| `battery sync` | Import edits from `BATTERY.md` into SQLite |
| `battery forget <id>` | Tombstone a memory |
| `battery serve` | Start MCP server (stdio) |
| `battery setup --client all` | Register MCP in Cursor / Claude |
| `battery profile create\|list` | Manage context profiles |
| `battery profile export\|import\|inspect` | Portable `.battery-bundle` backup/restore |
| `battery use <profile>` | Switch active profile |
| `battery hook install\|uninstall` | Claude Code lifecycle hooks |
| `battery git install\|capture` | Git post-commit episodic capture |
| `battery handoff export\|load\|show` | Cross-tool session handoff (Cursor ↔ Claude) |
| `battery checkpoint list\|show` | Inspect session checkpoints |
| `battery prune [--dry-run]` | Remove stale file-cited memories |
| `battery doctor [--adoption]` | Health and setup diagnostics |
| `battery eval [--real]` | Run retrieval benchmarks |

---

## How it works

```text
  Cursor / Claude / Gemini / CLI
              │
              ▼  MCP (stdio)
  ┌───────────────────────────┐
  │  recall · save · forget   │
  └───────────┬───────────────┘
              │
     ┌────────┴────────┐
     ▼                 ▼
 Hybrid RRF         BATTERY.md
 BM25 + Vector      (git mirror)
     │
     ▼
 SQLite WAL · FTS5 · sqlite-vec · local ONNX embeddings
```

**Why hybrid search?** Vectors miss exact tokens (`port 5432`, function names). BM25 misses semantic intent. Battery runs both and fuses ranks with Reciprocal Rank Fusion — tuned on real engineering memories ([RRF report](src/battery/evals/rrf_tuning_report.md)).

**Why SQLite?** Single-file portability, WAL concurrency, zero network latency, no Redis/Qdrant/Chroma server to run.

Deep dives: [Architecture Decision Records](docs/adr/) · [Product roadmap](docs/roadmap/PRODUCT_ROADMAP.md) · [Systems design notes](docs/design/)

---

## Retrieval benchmarks

Real-world corpus (92 engineering memories, 30 developer queries — `battery eval --real`):

| Strategy | Hit@1 | MRR | p50 latency |
|----------|------:|----:|------------:|
| BM25 (FTS5) | 80.0% | 0.86 | 0.6ms |
| Vector (sqlite-vec) | 83.3% | 0.89 | 25.3ms |
| **Battery hybrid (adaptive RRF)** | **86.7%** | **0.91** | 25.3ms |

Full reports: [`realworld_benchmark_report.md`](src/battery/evals/realworld_benchmark_report.md) · [`stress_test_report.md`](src/battery/evals/stress_test_report.md)

---

## Development

```bash
uv run pytest -v          # 57 tests
uv run battery doctor     # local health check
```

---

## Documentation

| Doc | Contents |
|-----|----------|
| [Product roadmap](docs/roadmap/PRODUCT_ROADMAP.md) | Priorities, market validation, v0.2+ plan |
| [ADRs](docs/adr/) | Storage, retrieval, MCP, profiles, runtime stack |
| [Master spec](docs/design/battery-master-spec.md) | Full system specification |
| [BATTERY.md example](BATTERY.md) | Living mirror format |

---

## Author

**Ajas Bakran** — AI systems engineer focused on agent evaluation, context engineering, and production reliability.

- GitHub: [github.com/DTiapan](https://github.com/DTiapan)
- LinkedIn: [linkedin.com/in/ajasbakran](https://linkedin.com/in/ajasbakran)
- Newsletter: [growithai.substack.com](https://growithai.substack.com/)

Advisory and consulting on AI agent reliability, memory architectures, and MCP integrations — [get in touch](mailto:bakran.ajas@gmail.com).

---

## License

[MIT](LICENSE)
