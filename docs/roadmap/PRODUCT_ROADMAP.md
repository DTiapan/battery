# Battery Product Roadmap: Solving Real-World AI Coding Agent Context Problems

> **Status:** Active / Living Document  
> **Revision:** v2 — reprioritized after cross-market validation (HN, Reddit, GitHub, research)  
> **Framework Alignment:** [Product Manager Toolkit](../../.agents/skills/product-manager-toolkit/SKILL.md) & [Roadmap Communicator](../../.agents/skills/roadmap-communicator/references/roadmap-templates.md)  
> **Last Updated:** 2026-09-12  

---

## Revision Summary (v1 → v2)

| Change | Rationale |
|---|---|
| Added **Shipped (v0.1)** section | ADR-0003 through ADR-0006 foundation is implemented; roadmap was listing shipped work as active NOW |
| **Session lifecycle hooks** promoted to NOW #1 | Community pain clusters on *session boundaries*, not commit boundaries ([r/ClaudeCode](https://www.reddit.com/r/ClaudeCode/comments/1qn5tfc/), [MemoTrail HN](https://news.ycombinator.com/item?id=47078938)) |
| **Stale invalidation** promoted from NEXT → NOW #2 | Auto-capture without anti-rot amplifies context poisoning ([Verified Repo Memory](https://glama.ai/mcp/servers/cognitivemyriad/verified-repo-memory-mcp), [AgentPatterns stale RAG](https://agentpatterns.ai/context-engineering/stale-repository-retrieval-induces-incorrect-code/)) |
| **Cross-tool handoff** promoted from LATER → NEXT | Core polyglot thesis; developers already build this manually ([handoff](https://github.com/zhangluka/handoff), [Passoff MCP](https://github.com/TheMrGU/Ai-Agent-Context-Passoff)) |
| **Git post-commit capture** demoted to NEXT adjunct | Useful episodic signal, but lower leverage than session hooks for P1/P4 |
| RICE scores recalibrated | Confidence lowered where estimates lack primary user interviews (per PM toolkit validation checklist) |

---

## 1. Executive Summary & Vision

**Battery** is a local-first, zero-cloud episodic and semantic memory engine for AI coding assistants (Claude Code, Cursor, Codex, Windsurf, Aider, and custom MCP-native agents).

Frontier LLM coding agents fail not because of reasoning limitations, but because of **context architecture failures**:

1. **Session Amnesia** — every new session starts from zero; polyglot workflows re-explain the same architecture daily.
2. **Context Poisoning & Rot** — recalled memories reference deleted files, obsolete APIs, or superseded decisions.
3. **Compaction Amnesia** — long-horizon runs lose constraints when the context window compacts mid-session.
4. **Manual Capture Friction** — explicit `save_memory` calls do not scale; capture must be event-driven.
5. **Static File Rot** — `CLAUDE.md` / `AGENTS.md` sprawl, drift, and contradict each other across tools.

Battery addresses these with on-device hybrid search (BM25 + dense vectors + RRF), a git-committable living mirror (`BATTERY.md`), MCP-native tool/resource/prompt surfaces, and **paired capture + invalidation** lifecycle management.

**North Star:** A developer switches from Cursor to Claude Code (or starts a new session) and the agent resumes with verified, current project context — without manual copy-paste and without stale hallucinations.

---

## 2. Market Research & Problem Discovery

Grounded in public developer discussions (September 2026 cross-check). Confidence tiers reflect **secondary** evidence unless noted.

```
                  ┌─────────────────────────────────────────────────────────┐
                  │              Real-World Developer Pain Points           │
                  └───────────────────────────┬─────────────────────────────┘
                                              │
    ┌─────────────────┬───────────────────────┼───────────────────────┬─────────────────┐
    ▼                 ▼                       ▼                       ▼                 ▼
┌───────────┐  ┌──────────────┐  ┌────────────────────┐  ┌─────────────┐  ┌──────────────┐
│ Session   │  │ Context Rot  │  │ Compaction         │  │ Manual      │  │ Cross-Tool   │
│ Amnesia   │  │ & Poisoning  │  │ Amnesia            │  │ Friction    │  │ Handoff Gap  │
│ P1        │  │ P2           │  │ P4                 │  │ P3          │  │ P6 (new)     │
└───────────┘  └──────────────┘  └────────────────────┘  └─────────────┘  └──────────────┘
```

### Empirical Problem Clusters

| ID | Problem Statement | Source Evidence | Confidence | Impact |
|---|---|---|---|---|
| **P1** | **Session amnesia** | [r/ClaudeCode](https://www.reddit.com/r/ClaudeCode/comments/1qn5tfc/), [r/cursor](https://www.reddit.com/r/cursor/comments/1tywmom/), [HN Agent Recall](https://news.ycombinator.com/item?id=47165499) | **High** | Re-explain conventions, architecture, and blockers every session |
| **P2** | **Context rot & poisoning** | [arxiv context rot study](https://arxiv.org/html/2607.17937), [LogRocket context rot](https://blog.logrocket.com/context-rot-slowing-down-your-ai-agent-how-fix/), stale RAG research | **High** | Agent writes code against deleted APIs or obsolete schemas |
| **P3** | **Manual capture friction** | [HN PMB auto-capture](https://news.ycombinator.com/item?id=48631169), [remem-mcp hooks](https://github.com/tinhien11/remem-mcp) | **High** | Memory tools unused if capture depends on user prompting |
| **P4** | **Compaction amnesia** | [DEV context loss guide](https://dev.to/whoffagents/why-your-claude-code-sessions-keep-losing-context-and-how-to-fix-it-nia), [claude-session-handoff-plugin](https://github.com/mehmeteminduran/claude-session-handoff-plugin) | **High** | Mid-session compaction silently drops decisions and rejected approaches |
| **P5** | **Multi-project isolation** | ADR-0006 rationale; enterprise consulting patterns | **Medium** | Cross-repo memory bleed; confidential context leakage |
| **P6** | **Cross-tool handoff gap** | [zhangluka/handoff](https://github.com/zhangluka/handoff), [trevhud/handoff](https://github.com/trevhud/handoff), [Passoff MCP](https://github.com/TheMrGU/Ai-Agent-Context-Passoff) | **High** | Cursor session invisible to Claude Code; polyglot tax persists |
| **P7** | **Static instruction file rot** | [CLAUDE.md sprawl (DEV)](https://dev.to/takashimatsuyama/ending-the-claudemd-agentsmd-copilot-instructionsmd-sprawl-declare-one-source-verify-the-1gbb), [maintenance guide](https://mcp.directory/blog/claude-md-agents-md-maintenance-2026) | **High** | Agents trust stale rules; multiple files diverge silently |

### Competitive Landscape (September 2026)

| Project | Strength | Battery differentiation |
|---|---|---|
| [gingugu](https://github.com/gingugu/gingugu) | Mature local SQLite brain, staleness hints, 400+ tests | Battery: eval-tuned RRF, `BATTERY.md` git mirror |
| [remem-mcp](https://github.com/tinhien11/remem-mcp) | Lifecycle hooks, compaction survival, error learning | Battery: hybrid retrieval + living mirror; **gap: hooks** |
| [Verified Repo Memory](https://glama.ai/mcp/servers/cognitivemyriad/verified-repo-memory-mcp) | JIT file verification before recall | Battery: broader semantic memory; **gap: JIT verify** |
| [MemoTrail](https://news.ycombinator.com/item?id=47078938) | Session log indexing | Battery: structured decisions/rules, not just transcripts |
| [Engram-MCP](https://github.com/TomOst-Sec/Engram-MCP) | Codebase architecture + git history | Battery: sovereign project memory, not code indexing |

**Strategic wedge:** Battery is not "another vector DB." It is **git-committable, polyglot, locally sovereign memory with tuned hybrid retrieval** — differentiated by the capture → verify → recall loop, not storage alone.

---

## 3. Shipped — v0.1 Foundation ✅

The following ADR decisions are **implemented and tested** (September 2026). They are no longer roadmap items.

| Capability | ADR | CLI / MCP Surface | Verification |
|---|---|---|---|
| SQLite WAL + FTS5 + `sqlite-vec` hybrid retrieval | [ADR-0003](../adr/0003-storage-and-retrieval-engine.md) | `battery query`, `recall_memory` | `tests/test_retrieval.py`, RRF tuning report |
| Local ONNX embeddings (`all-MiniLM-L6-v2`) | [ADR-0004](../adr/0004-embedding-strategy-and-vector-pipeline.md) | automatic on save/recall | `tests/test_db.py` |
| MCP server (tools + resources + prompts) | [ADR-0005](../adr/0005-mcp-interface-and-living-markdown-mirror.md) | `battery serve`, `recall_memory`, `save_memory`, `forget_memory`, `list_memories`, `battery://context`, `battery://rules` | `tests/test_mcp.py` |
| Living Markdown mirror (`BATTERY.md`) | [ADR-0005](../adr/0005-mcp-interface-and-living-markdown-mirror.md) | `battery sync`, auto-export on mutation | `tests/test_sync.py` |
| Multi-battery context profiles | [ADR-0006](../adr/0006-multi-battery-context-profiles.md) | `battery profile *`, `battery use`, `--profile` | `tests/test_profile.py` |
| SHA-256 content deduplication | [ADR-0003](../adr/0003-storage-and-retrieval-engine.md) | transparent on insert | `tests/test_db.py` |
| Client setup helper | — | `battery setup --client all` | `tests/test_cli.py` |
| Real-world retrieval eval harness | — | `battery evaluate` | `src/battery/evals/` |

**Known v0.1 gaps (intentionally deferred):** no lifecycle hooks, no stale invalidation, no session handoff export, no semantic near-dedup merge.

---

## 4. RICE Prioritization Matrix (v2)

Scored per [frameworks.md](../../.agents/skills/product-manager-toolkit/references/frameworks.md). **Reach** estimates assume early-adopter MCP users (500–2,500 sessions/quarter); revisit after 5+ user interviews.

$$\text{RICE Score} = \frac{\text{Reach} \times \text{Impact} \times \text{Confidence}}{\text{Effort}}$$

| Initiative | Reach | Impact | Conf. | Effort | RICE | Class | Problems |
|---|---|---|---|---|---|---|---|
| **A. Session Lifecycle Hooks** (SessionStop + PreCompact) | 2,500 | Massive (3.0) | Medium (0.8) | S (3) | **2,000** | 🚀 Quick Win | P1, P3, P4 |
| **B. Git-Aware Stale Invalidation** (`battery prune` + JIT verify on recall) | 2,000 | Massive (3.0) | Medium (0.8) | S (3) | **1,600** | 🚀 Core Health | P2 |
| **C. MCP Resource Adoption Path** (setup docs + session-start injection) | 2,000 | High (2.0) | High (1.0) | XS (1) | **4,000** | 🚀 Quick Win | P3, P7 |
| **D. Cross-Tool Session Handoff Export** | 1,800 | High (2.0) | Medium (0.8) | M (5) | **576** | 🎯 Strategic Bet | P1, P6 |
| **E. Near-Duplicate Consolidation** (`similarTo` merge) | 1,500 | Medium (1.0) | High (1.0) | S (3) | **500** | 📈 Medium | Token efficiency |
| **F. Git Post-Commit Episodic Capture** | 1,200 | Medium (1.0) | Medium (0.8) | XS (1) | **960** | 📈 Medium | P1 (adjunct) |
| **G. Architectural Guardrail Enforcement** | 1,400 | High (2.0) | Low (0.5) | M (5) | **280** | 🎯 Strategic Bet | P7 |
| **H. Battery Doctor CLI** | 600 | Low (0.5) | High (1.0) | XS (1) | **300** | 🔧 Fill-In | Ops |
| **I. Go V2 Daemon** (ADR-0002 Phase 2) | 800 | High (2.0) | Medium (0.8) | XL (13) | **98** | 🔮 Platform | Performance |

### Sequencing Rule (non-negotiable)

> **Never ship bulk auto-capture (A or F) without stale invalidation (B) in the same release train.**

Auto-capture increases memory volume; without invalidation, P2 worsens. Initiatives A + B + C ship as a **paired release**.

### Value vs. Effort Matrix (v2)

```
                      Low Effort (XS – S)              High Effort (M – XL)
                 +------------------------------+------------------------------+
                 |         QUICK WINS             |         STRATEGIC BETS         |
   High Value    | • MCP Resource Adoption (C)    | • Cross-Tool Handoff (D)     |
  (Massive/High) | • Session Lifecycle Hooks (A)  | • Guardrail Enforcement (G)  |
                 | • Stale Invalidation (B)       |                              |
                 +------------------------------+------------------------------+
                 |         MEDIUM PRIORITY        |         PLATFORM             |
   Med/Low Value  | • Git Post-Commit (F)          | • Go V2 Daemon (I)           |
                 | • Near-Dedup Merge (E)         |                              |
                 | • Battery Doctor (H)           |                              |
                 +------------------------------+------------------------------+
```

---

## 5. Now / Next / Later Strategic Roadmap

Per [Now / Next / Later](../../.agents/skills/roadmap-communicator/references/roadmap-templates.md) — direction without false precision.

### 🟢 NOW — Capture + Verify Loop (Active Sprint)

*Theme: **Frictionless, trustworthy memory.*** Pair ingestion with invalidation before scaling volume.

#### NOW-1: Session Lifecycle Hooks (`battery hook install`)

| | |
|---|---|
| **Problems** | P1 Session amnesia, P3 Manual friction, P4 Compaction amnesia |
| **Deliverable** | `battery hook install` registers agent lifecycle hooks: **SessionStop** (structured checkpoint) and **PreCompact** (preserve decisions before context compaction). Checkpoints capture: task summary, decisions made, rejected approaches, changed files, blockers, next step. |
| **Out of scope (v1 hooks)** | Full transcript indexing (see MemoTrail pattern in NEXT); LLM-generated summaries (use structured extraction first). |
| **Success metrics** | ≥90% of ended sessions produce a checkpoint; PreCompact fires before 100% of compactions in Claude Code test matrix; hook execution <200ms p95. |
| **Dependencies** | MCP `save_memory` + episodic category schema; optional `.battery/handoff/` directory |
| **Reference implementations** | [remem-mcp PreCompact](https://github.com/tinhien11/remem-mcp), [handoff-mcp hooks](https://github.com/alphaelements/handoff-mcp), [claude-session-handoff-plugin](https://github.com/mehmeteminduran/claude-session-handoff-plugin) |

#### NOW-2: Git-Aware Stale Memory Invalidation (`battery prune` + JIT verify)

| | |
|---|---|
| **Problems** | P2 Context rot & poisoning |
| **Deliverable** | Extend memory schema with optional `file_paths[]` and `content_hash_at_save`. On recall, JIT-verify cited files against current disk state. `battery prune` scans git history + filesystem and tombstones or decays memories referencing deleted/changed symbols. |
| **Success metrics** | 0 stale-recall failures on extended `evals/generate_realworld_data.py` rot scenarios; JIT verify adds <10ms p95 to recall path. |
| **Dependencies** | Ship alongside NOW-1 (sequencing rule) |
| **Reference implementations** | [Verified Repo Memory MCP](https://glama.ai/mcp/servers/cognitivemyriad/verified-repo-memory-mcp) |

#### NOW-3: MCP Resource Adoption Path

| | |
|---|---|
| **Problems** | P3 Manual friction, P7 Static file rot |
| **Deliverable** | Document and automate session-start context loading: `battery setup` ensures MCP resources (`battery://context`, `battery://rules`) and `battery-context` prompt are wired in Claude Desktop + Cursor configs. Add `battery doctor --adoption` check: "Are resources reachable? Is `BATTERY.md` in sync?" |
| **Success metrics** | New user reaches working recall in <5 min via `battery setup`; resources return non-empty context on fresh install with seed memories. |
| **Dependencies** | Already implemented in ADR-0005 — this is adoption/UX, not new engine work |
| **Effort** | XS — highest RICE score in portfolio |

---

### 🟡 NEXT — Polyglot Continuity & Efficiency (1–2 Quarters)

*Theme: **Memory that follows the developer across tools and commits.***

#### NEXT-1: Cross-Tool Session Handoff Export

| | |
|---|---|
| **Problems** | P1, P6 Cross-tool handoff gap |
| **Deliverable** | Structured handoff artifact (markdown + metadata) exportable from Battery and loadable by any MCP client. Fields: `from_client`, `to_client`, decisions, dead-ends, changed files, verification status, next action. CLI: `battery handoff export` / `battery handoff load --latest`. |
| **Success metrics** | Cursor → Claude Code switch resumes mid-task without re-explanation in scripted eval scenario; handoff lineage traceable across ≥3 hops. |
| **Dependencies** | NOW-1 checkpoint schema |

#### NEXT-2: Near-Duplicate Consolidation (`similarTo`)

| | |
|---|---|
| **Problems** | Token bloat from repeated capture |
| **Deliverable** | On `save_memory`, cosine similarity check against existing active memories. If similarity > 0.88, merge/update instead of insert; return `{ similarTo: id }`. |
| **Success metrics** | ≥40% reduction in duplicate rows on stress corpus re-ingestion; no recall MRR regression. |
| **Note** | SHA-256 exact dedup already shipped; this adds semantic near-dedup. |

#### NEXT-3: Git Post-Commit Episodic Capture (Adjunct)

| | |
|---|---|
| **Problems** | P1 (partial) — captures committed work only |
| **Deliverable** | Optional `post-commit` hook: index commit message + changed file list + diff stat summary as episodic memory tagged with `commit_sha`. |
| **Success metrics** | 100% commits captured when hook enabled; <150ms hook time; no false stale invalidation from NOW-2. |
| **Positioning** | **Adjunct** to session hooks — captures architectural commits, not in-session decisions. |

#### NEXT-4: Session Log Ingestion (Optional Collector)

| | |
|---|---|
| **Problems** | P1 — developers want "what did we discuss yesterday?" |
| **Deliverable** | Read-only collectors for Claude Code (`~/.claude/projects/`) and Cursor agent transcripts; chunk + embed as searchable episodic memories. |
| **Success metrics** | Recall finds prior session decisions in ≥85% of benchmark queries. |
| **Risk** | Privacy/noise — opt-in per project; exclude raw tool traces by default. |

---

### 🔵 LATER — Governance & Platform (2+ Quarters)

*Theme: **Enforcement and performance at scale.***

| Initiative | Problem | Deliverable |
|---|---|---|
| **Architectural Guardrail Enforcement** | P7 | High-priority invariant tier + PreToolUse hook integration (enforce via shell, not prose — per [MCP.directory guidance](https://mcp.directory/blog/claude-md-agents-md-maintenance-2026)) |
| **Battery Doctor CLI** | Ops | `battery doctor`: sqlite-vec integrity, embedding cache, dimension mismatch, orphan vectors |
| **Autonomous Session Summarizer (LLM-assisted)** | P4 | Optional local Ollama summarization of checkpoints into hierarchical memory (L1 summary → L3 detail on demand; [hmem pattern](https://news.ycombinator.com/item?id=47103237)) |
| **Go V2 Daemon** | Platform | ADR-0002 Phase 2: single binary, UDS multi-client, <5ms cold start |
| **Cross-Profile Search** | P5 edge case | Explicit opt-in federated recall across profiles |
| **Research Publication** | Impact & credibility | See [§8 Research & External Impact](#8-research--external-impact-long-term-goal) |

---

## 8. Research & External Impact (Long-Term Goal)

> **Status:** Deferred — not a near-term build priority.  
> **North star:** Real user impact first; publication follows evidence, not the reverse.

Battery is **not yet submission-ready** as a novel-methods paper. Core components (hybrid RRF, sqlite-vec + FTS5, MCP memory, git-committable markdown, adaptive fusion) overlap prior art including vstash, QARF, OwnMem, MemForge, and Git Context Controller. A credible publication path requires **integration + measurement** claims backed by comparative evals, not “we invented hybrid search.”

### When to pursue

| Gate | Requirement |
|------|-------------|
| **G1 — Product proof** | Capture → verify → handoff loop shipped and validated (O1 + O2 OKRs green on scorecard) |
| **G2 — Comparative eval** | Head-to-head on open harness vs fixed RRF, IDF-adaptive RRF, and ≥1 markdown-only baseline |
| **G3 — End-to-end signal** | At least one standard external benchmark (e.g. LongMemEval-S retrieval or agent task ablation) |
| **G4 — Artifact** | Reproducible harness + paper positioning memo (contributions, related work, honest deltas) |

### Plausible framing (when gates pass)

- **Systems / workshop track:** local-first memory substrate for polyglot coding agents — living mirror + tiered SQLite + MCP lifecycle.
- **Benchmark track:** real-world coding-agent memory eval harness (92 ADR-grounded memories, 30 dev queries).
- **Not claiming:** novel hybrid retrieval algorithm (prior art exists).

### Sequencing

1. Ship and measure user-facing pain relief (NOW-3 adoption, Sprint C rot/handoff evals).  
2. Open eval harness + baseline comparisons.  
3. Draft related-work matrix; only then target workshop or arXiv systems note.

**Owner checkpoint:** Revisit after Sprint C complete and 5+ user interviews (roadmap validation debt).

---

## 6. OKR & Metric Cascades (v2)

| Objective | Key Results | Initiatives |
|---|---|---|
| **O1: Eliminate session amnesia** | KR 1.1: MRR ≥ 0.85 on real-world eval harness<br>KR 1.2: ≥90% sessions produce lifecycle checkpoint without manual `save_memory`<br>KR 1.3: Cross-tool handoff eval passes (Cursor ↔ Claude) | NOW-1, NEXT-1 |
| **O2: Zero context poisoning** | KR 2.1: 0 stale-recall failures on rot benchmark suite<br>KR 2.2: JIT verify <10ms p95 on recall<br>KR 2.3: Invalidation ships in same release as auto-capture | NOW-2 |
| **O3: Frictionless adoption** | KR 3.1: `battery setup` → working recall in <5 min<br>KR 3.2: MCP resources loaded at session start in documented client configs<br>KR 3.3: `BATTERY.md` git-diff reviewable in PRs | NOW-3, shipped ADR-0005 |
| **O4: Sub-50ms local performance** | KR 4.1: p95 hybrid search <45ms on developer laptop<br>KR 4.2: 100% offline; zero cloud embedding calls | Shipped ADR-0003/0004 |

---

## 7. Stakeholder Summaries

### To Engineering

The v0.1 engine (hybrid retrieval, MCP, profiles, sync) is **done**. The next sprint is the **capture + verify loop**:

1. **Session hooks** — highest user-validated leverage; reuse existing `save_memory` pipeline.
2. **Stale invalidation** — **must ship with hooks**; extend schema + recall path, not a separate subsystem.
3. **Adoption UX** — thin layer on existing MCP resources; ship docs + `battery doctor --adoption`.

Do **not** start Go V2 rewrite until the capture → verify → handoff loop has real usage signal.

### To Users & Developers

Battery already stores and retrieves your project rules locally. Next, it will **remember your sessions automatically**, **invalidate stale facts when code changes**, and **hand off context when you switch tools** — without maintaining rotting `CLAUDE.md` copies in every IDE.

### To Product / PM

**Validation debt:** RICE reach/impact numbers are directional, not interview-backed. Before v0.2 launch, run 5–8 developer interviews (mix of Cursor + Claude Code power users and churned memory-tool users) and update confidence scores. Track: sessions/week with checkpoint, stale-recall error rate, handoff success rate.

---

## 8. Explicit Non-Goals (v0.2)

| Non-Goal | Reason |
|---|---|
| Cloud sync / team server | Privacy sovereignty constraint (ADR-0005) |
| Full codebase indexing (tree-sitter) | Engram/codebase-memory-mcp territory; different product |
| Replacing `CLAUDE.md` entirely | Battery complements static rules; living mirror reduces but does not eliminate curated invariants |
| LLM-on-every-write consolidation | Latency + cost; structured hooks first, LLM summarization in LATER |
| Go rewrite before product validation | ADR-0002 Phase 2 deferred until capture loop proven |

---

## 9. Document History

| Version | Date | Author | Changes |
|---|---|---|---|
| v1 | 2026-09-11 | — | Initial roadmap; git hooks NOW, profiles NOW |
| v2 | 2026-09-12 | — | Reprioritized after market cross-check; added Shipped section, P6, sequencing rule, revised RICE |
