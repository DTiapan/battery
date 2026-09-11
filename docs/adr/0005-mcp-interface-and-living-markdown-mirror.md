# ADR 0005: MCP Interface and Living Markdown Mirror

## Status
Accepted

## Date
2026-09-11

## Context
The primary failure mode of proprietary memory solutions (such as ChatGPT Memory or Claude Project Memory) is that they lock the user's context into a black-box silo. Developers cannot export, inspect, version-control, or share their memory state across different tools.

Furthermore, developers deeply value transparency: if an AI memory engine stores decisions in an opaque binary database, users lose trust and cannot easily audit or prune stale or incorrect rules.

To solve this, the Battery Context Engine must serve two interfaces simultaneously:
1. A standardized machine-to-machine interface (**Model Context Protocol / MCP**) for LLM clients (Cursor, Claude Desktop, Gemini CLI).
2. A transparent, human-first interface (**`BATTERY.md` Living Markdown Mirror**) for git versioning, manual review, and direct editing.

## Decision Drivers
* **Cross-Client Standard:** Must integrate seamlessly with any MCP-compliant AI client without proprietary plugins.
* **Low Tool Overhead:** Tool signatures must be compact, intuitive, and unambiguous to prevent LLMs from wasting tokens or hallucinating arguments.
* **Human Sovereignty & Version Control:** Memory state must be readable in plain text, editable in any code editor, and committable to git repositories alongside project code.
* **Bidirectional Consistency:** Edits made in the markdown file must reflect in the database, and memory updates made by the agent must update the markdown file.

## Considered Options

### Option 1: Opaque Database with REST / CLI Only
* **Pros:** Simpler architecture with no file-synchronization complexity.
* **Cons:** Zero transparency for users; cannot commit memories to git; no standard MCP integration.

### Option 2: Pure MCP Server over Stdio (Database-Only)
* **Pros:** Standard MCP client support.
* **Cons:** Lacks a visible artifact in the workspace; developers cannot audit what the LLM remembered without running SQL queries.

### Option 3: Standard MCP Server + Bidirectional `BATTERY.md` Living Mirror
* **Pros:**
  * **For Agents:** Clean MCP tool suite (`recall_memory`, `save_memory`, `forget_memory`, `list_memories`) accessible via standard Stdio transport.
  * **For Humans:** A curated `BATTERY.md` file at the root of the project reflecting active decisions, rules, and facts in structured Markdown.
  * **Git-Native:** `BATTERY.md` can be committed, code-reviewed in pull requests, and shared across engineering teams.
  * **Sync Engine:** Automatic generation on database mutations + file hash tracking to parse manual human edits back into SQLite.
* **Cons:** Requires change-detection logic to prevent write loops between SQLite and `BATTERY.md`.

## Decision
We select **Option 3: Standard MCP Server with Bidirectional `BATTERY.md` Living Mirror**.

### 1. Exposed MCP Tool Contracts

```python
recall_memory(query: str, limit: int = 5, category: str | None = None) -> list[dict]
"""
Searches the user's sovereign context engine using hybrid BM25 + vector search.
Returns matching memories ranked by Reciprocal Rank Fusion (RRF) with relevance scores.
"""

save_memory(content: str, category: str = "decision", tags: list[str] = []) -> dict
"""
Persists a new architectural decision, project rule, user preference, or fact.
Computes SHA-256 deduplication, creates embeddings, and updates the BATTERY.md mirror.
"""

forget_memory(memory_id: str) -> dict
"""
Tombstones an existing memory by ID, preventing it from appearing in future queries.
"""

list_memories(category: str | None = None, limit: int = 20) -> list[dict]
"""
Browses stored memories chronologically or filtered by category (rule, decision, preference).
"""
```

### 2. Exposed MCP Resources (Proactive Context Injection)

To mitigate LLM laziness (where models skip reactive `recall_memory` tool calls when overconfident), Battery exposes read-only MCP Resources that clients (Claude Desktop, Cursor, Gemini) can auto-fetch or attach at session initialization:

* `battery://context` (`text/markdown`): Curated active sovereign context. Groups active constraints by `Active Rules & Constraints`, `Architectural Decisions`, `User Preferences & Workflow Habits`, and `General Context & Knowledge` sorted by `importance DESC, id DESC`.
* `battery://rules` (`text/markdown`): High-priority active project rules and hard constraints only.

### 3. Exposed MCP Prompts (Session Initialization)

* `battery-context(task: str = "")`: A structured system prompt that injects:
  1. Sovereign memory directives instructing the agent to consult `recall_memory` and persist invariants with `save_memory`.
  2. Critical active rules and constraints (top priority).
  3. Dynamic task-relevant memories retrieved via Reciprocal Rank Fusion hybrid search when `task` is specified, or baseline architectural decisions when omitted.

### 4. Living Mirror Specification (`BATTERY.md`)
Whenever a memory event is committed to SQLite:
1. The engine formats the active memory set grouped by categories:
   * `# Project Memory & Architecture Invariants`
   * `## Active Rules & Constraints`
   * `## Decisions & Architectural Choices`
   * `## User Preferences & Workflow Habits`
2. Writes atomically to `BATTERY.md` using a temporary swap file.
3. Computes the SHA-256 hash of `BATTERY.md` to distinguish agent-generated writes from external human edits.

## Consequences

### Positive
* Zero lock-in: Any MCP-compatible agent can immediately read and write context.
* Complete developer transparency: A single human-readable file tracks project memory in git.
* Team sharing: Checking `BATTERY.md` into git allows entire teams to share the exact same project context across different AI tools.

### Negative
* File system write-watchers require debouncing (200ms) to avoid thrashing during rapid edits.
