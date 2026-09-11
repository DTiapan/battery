# Battery Context Engine — Master Document

> **Living document.** All architectural decisions, their rationale, and the evolution of thinking are recorded here so we can trace *how* we arrived at every choice.
> **All docs live in:** `./`
> **Last updated:** 2026-09-11

---

## 1. The Problem

### 1.1 One-Line Problem Statement
> LLMs are stateless silos. Every tool switch costs context. Users pay the price in wasted time, repeated explanations, and stale contradictions across models.

### 1.2 Evidence of Real Pain

| Signal | Source | Magnitude |
|---|---|---|
| Reddit r/LocalLLaMA & r/ChatGPT describe "AI busywork" | Community research (2026-09-11) | Top complaint in polyglot AI workflows |
| Anthropic built Claude memory; OpenAI built ChatGPT memory | Competitor moves | Both admit memory is a product-level problem |
| `CLAUDE.md`, `.cursorrules`, `AGENTS.md` proliferated organically | Developer behavior | Users invented static workarounds because dynamic tools didn't exist |
| Three arXiv papers (2025–2026) specifically on "portable agent memory" | Academic signal | Active unsolved research area |
| Mem0 raised funding; Letta (MemGPT) spun out; Zep launched | Market moves | Enough commercial validation to prove demand |

### 1.3 The Specific Failure Modes

```
Failure Mode 1: Model Switch Tax
  User: [Explains entire project in Cursor/Claude]
  User switches to Gemini for large-file analysis
  Gemini: "I don't know your project's tech stack."
  Cost: 5–15 minutes re-prompting per switch.

Failure Mode 2: Context Drift (Contradictory Memory)
  Monday: "We decided to use PostgreSQL."  [Stored in Claude chat]
  Wednesday (new session): "Should we use Postgres or DynamoDB?"
  Model suggests DynamoDB. User has forgotten Monday's decision.
  Cost: Re-debates settled questions; inconsistent codebase decisions.

Failure Mode 3: Agent Amnesia
  Autonomous agent runs. Produces findings. Session ends.
  Next run: Agent starts with zero knowledge of prior run outputs.
  Cost: Repeated work; no accumulation of domain knowledge.

Failure Mode 4: Privacy Lock-in
  User cannot use cloud memory (ChatGPT, Claude) for sensitive work.
  Static files (CLAUDE.md) are manual and don't scale across tools.
  Cost: Sensitive domain users (healthcare, legal, finance) have no option.
```

---

## 2. The Solution

### 2.1 Core Thesis
> Decouple stateful memory from stateless LLM compute. The LLM is commodity compute (the motor). User context, decisions, and domain knowledge are the sovereign asset (the battery). Swap the battery across any motor via a standard protocol.

### 2.2 What Battery Is (and Is Not)

| Battery IS | Battery IS NOT |
|---|---|
| A local-first persistent context store | A cloud memory service |
| A Model Context Protocol (MCP) server | A replacement for the LLM |
| A CLI tool you own and inspect | A black-box AI product |
| Human-readable (`BATTERY.md`) + machine-fast (SQLite) | Schema-locked proprietary format |
| Model-agnostic (works with any OpenAI-compat model) | Tied to Claude, Gemini, or OpenAI |

### 2.3 How It Works (30-second version)

```
┌─────────────────────────────────────────────────────────────┐
│              YOUR LOCAL MACHINE                             │
│                                                             │
│   Claude Desktop ──┐                                        │
│   Cursor       ────┼──► Battery Daemon ──► SQLite DB        │
│   Gemini CLI   ────┤    (MCP Server)       (battery.db)     │
│   Your Scripts ────┘         │                              │
│                              ▼                              │
│                        BATTERY.md  ◄──► You (human editor)  │
└─────────────────────────────────────────────────────────────┘
```

1. **Save:** Any connected tool calls `save_memory("We use Go 1.24, strict WAL mode")`
2. **Recall:** Any connected tool calls `recall_memory("what's our DB setup?")` and gets the right answer in <50ms
3. **Inspect:** Open `BATTERY.md` in your editor to read, edit, or delete any memory with your keyboard
4. **Switch tools:** New tool connects to the same daemon — zero re-explaining

---

## 3. Methodology (How We Build It)

### 3.1 Decided Architecture (Locked)

| Decision | Choice | Why |
|---|---|---|
| **Deployment model** | Persistent local daemon via **Unix Domain Socket (UDS)** | `stdio` MCP cannot serve multiple clients simultaneously — critical architectural constraint discovered in cross-verification |
| **Storage** | SQLite (WAL mode) + FTS5 (BM25) + `sqlite-vec` (vectors) | Single-file, zero-config, ACID, inspectable, embeddable |
| **Retrieval** | Hybrid: BM25 keyword + cosine vector, fused with Reciprocal Rank Fusion | Pure vector fails on code symbols/exact strings; pure BM25 misses semantic intent |
| **Decay/Eviction** | Ebbinghaus-inspired scoring + W-TinyLFU admission (count-min sketch) | Prevents context pollution from transient facts; keeps signal-to-noise high |
| **Embeddings** | Ollama local HTTP sidecar (primary); ONNX `all-MiniLM-L6-v2` (offline fallback) | No CGo complexity; leverages existing user tooling |
| **Prototype language** | Python + `uv` | Fastest path to validate hybrid retrieval quality |
| **Daemon language** | Go 1.24+ | Single binary, instant cold-start, Goroutine-based supervised workers |
| **Human interface** | Bidirectional `BATTERY.md` sync (Living Markdown) | Builds trust; git-committable; editable in any IDE |

### 3.2 Systems Engineering Foundations (What We Borrowed and Why)

| Borrowed From | Specific Primitive | Applied As |
|---|---|---|
| **Git** | Merkle DAG, content-addressable storage | Cross-model fact deduplication; context branching |
| **Kafka** | Append-only event log, per-consumer offsets | Immutable `memory_events` table; per-model catch-up on reconnect |
| **Redis** | ZSET scoring, dual expiry, pub/sub | In-memory ranking for top-K prompt injection; cross-client event broadcast |
| **Erlang/OTP** | Share-nothing actors, supervision trees | Isolated extraction workers; write path crashes never affect read path |
| **SQLite** | WAL mode, FTS5, zero-copy mmap | Core storage substrate |
| **Roaring Bitmaps** | SIMD-accelerated set intersections | Tag/category filtering before vector scan (μs-level candidate pruning) |
| **UDS (POSIX)** | Local IPC, `chmod 0600` file permissions | Secure, fast, zero-port multi-client daemon |

### 3.3 What We Explicitly Did Not Build (And Why)

| Rejected Component | Reason |
|---|---|
| Distributed Raft / Paxos consensus | Local-first single-host; SQLite WAL is sufficient |
| Neo4j / full graph DB | Relationship triples fit in relational SQL; graph engines require JVM + gigabytes of RAM |
| Memcached slab allocators | Operating on megabytes, not 64GB; modern allocators handle it |
| Cloud sync layer (v1) | Explicitly out of scope; privacy is a core constraint |

---

## 4. V1: What Gets Shipped

### 4.1 V1 Scope (Lean & Shippable)

**Goal:** A working local MCP server + CLI that connects to Claude Desktop and Cursor in under 5 minutes.

```
battery/
├── battery/
│   ├── __init__.py
│   ├── db.py           # SQLite init, FTS5 + sqlite-vec schema
│   ├── retrieval.py    # Hybrid BM25 + vector + RRF scorer
│   ├── embeddings.py   # Ollama HTTP client (with ONNX fallback)
│   ├── mcp_server.py   # MCP protocol handler over UDS + stdio
│   └── cli.py          # CLI entry point
├── BATTERY.md          # Human-readable mirror (auto-generated)
├── pyproject.toml      # uv-managed dependencies
└── mcp.json            # MCP client config snippet (copy to Claude Desktop)
```

### 4.2 V1 Feature Checklist

```
[ ] battery init          → Creates ~/.battery/battery.db with full schema
[ ] battery add "text"    → Saves a memory with optional -c category flag
[ ] battery list          → Pretty terminal table of all active memories
[ ] battery query "..."   → Hybrid BM25 + vector search with scored results
[ ] battery serve         → Starts MCP daemon on ~/.battery/battery.sock
[ ] battery forget <id>   → Tombstones a memory
[ ] BATTERY.md sync       → Auto-writes human-readable mirror on every change
```

### 4.3 MCP Tools Exposed (V1)

```python
@mcp.tool()
def recall_memory(query: str, limit: int = 5) -> list[dict]:
    """Search personal context, project rules, and decisions."""

@mcp.tool()
def save_memory(content: str, category: str = "general") -> dict:
    """Persist a rule, preference, or decision to local memory."""

@mcp.tool()
def forget_memory(memory_id: str) -> dict:
    """Tombstone a stored memory."""

@mcp.tool()
def list_memories(category: str = None, limit: int = 20) -> list[dict]:
    """Browse stored memories, optionally filtered by category."""
```

### 4.4 V1 Non-Goals (Deliberately Deferred)

| Feature | Deferred To |
|---|---|
| Context branching (`battery branch`) | V2 |
| Per-model consumer offset tracking | V2 |
| W-TinyLFU admission filtering | V2 (use simpler LRU for V1) |
| Ambient passive extraction | V2 |
| Browser extension | V3 |
| Multi-user / team sharing | V3 |

### 4.5 V1 Definition of Done

- [ ] `battery serve` connects to Claude Desktop and appears in tool list
- [ ] A fact saved in Cursor/Claude is recalled correctly in a fresh Claude Desktop session
- [ ] `BATTERY.md` updates within 1 second of any `save_memory` call
- [ ] All active memories survive a daemon restart
- [ ] `battery query "..."` returns correct results in <100ms on 1,000 facts

---

## 5. Will It Be Helpful?

### 5.1 Market Fit Assessment

| Dimension | Assessment |
|---|---|
| **Problem Real?** | Yes. Validated by Reddit/community signal, competitor moves (Mem0, Letta), developer workarounds (`.cursorrules`), and arXiv literature. |
| **Existing solutions sufficient?** | No. Mem0 is cloud-first. Letta is a heavy framework. Zep requires Docker + Postgres. Static markdown doesn't scale. |
| **Who benefits most, immediately?** | Developers using 2+ AI tools daily (Cursor + Claude Desktop is already >1M users). |
| **Privacy moat?** | Yes. Local-first, single-file SQLite, no cloud dependency makes it uniquely suitable for sensitive domains (healthcare, legal, finance, defense contractors). |
| **Distribution?** | MCP is already standard in Claude Desktop, Cursor, Zed, Windsurf, Antigravity. Zero integration work for users. |

### 5.2 Why This Beats Static Workarounds

```
CLAUDE.md / .cursorrules (current state of the art):
  ✅ Human-readable, git-tracked
  ✅ Works reliably
  ❌ 100% manual — you write every rule yourself
  ❌ Does not adapt or decay
  ❌ Cannot query or search
  ❌ Not shared across models

Battery (what we build):
  ✅ Human-readable (BATTERY.md mirror)
  ✅ Git-trackable
  ✅ LLM learns and saves rules automatically
  ✅ Hybrid search finds the right context for each query
  ✅ Stale facts decay; signal stays clean
  ✅ Shared across ALL connected tools via MCP
```

### 5.3 Honest Risks

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| LLM doesn't call `recall_memory` proactively | High | High | Use MCP Prompts/Resources to inject top-5 rules at session start (proactive, not reactive) |
| Users don't trust invisible memory | Medium | High | `BATTERY.md` living mirror is the trust mechanism |
| Ebbinghaus decay constants wrong | Medium | Medium | Expose `λ` and `τ` as config knobs; don't hard-code |
| Ollama not installed on all machines | Medium | Medium | ONNX fallback path handles this |
| Multi-writer SQLite contention | Low (V1 low volume) | Medium | Single-writer goroutine/channel in Go daemon |

---

## 6. Decision Log (How We Arrived Here)

| Date | Decision | Rationale | Alternatives Rejected |
|---|---|---|---|
| 2026-09-11 | Local-first over cloud | Privacy constraint; offline capability; data sovereignty | Cloud-hosted (Mem0, Zep) |
| 2026-09-11 | MCP as protocol | Already standard in all major AI tools; zero client integration work | Custom HTTP API, LSP-style protocol |
| 2026-09-11 | UDS daemon over `stdio` | `stdio` cannot be shared across multiple clients simultaneously | Per-client `stdio` subprocess |
| 2026-09-11 | SQLite over embedded graph DB | Simplicity; single file; inspectable; FTS5 built-in | Neo4j, DuckDB, Qdrant |
| 2026-09-11 | Hybrid BM25+Vector over pure vector | Code symbols, exact strings, file paths fail with pure vector search | Pure vector (Cosine only) |
| 2026-09-11 | Ollama sidecar over ONNX CGo | Eliminates CGo build complexity; users likely already run Ollama | Native ONNX with CGo |
| 2026-09-11 | Python/uv for prototype | Fastest validation of retrieval quality before Go rewrite | Go-first, Rust |
| 2026-09-11 | Living Markdown bridge | Trust interface; git-trackable; editable by human keyboard | Pure DB (no human mirror) |
