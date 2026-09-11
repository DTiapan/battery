# ADR 0002: Phased Implementation Stack (Python V1 Prototype to Go V2 Daemon)

## Status
Accepted

## Date
2026-09-11

## Context
The Battery Context Engine requires both rapid validation of novel algorithmic primitives (hybrid BM25 + dense vector + Reciprocal Rank Fusion, local embedding pipelines, and Model Context Protocol tool interfaces) and, ultimately, a production-grade, zero-dependency local daemon that starts instantaneously with negligible memory overhead.

Building directly in a low-level compiled language like Go or Rust from day one risks spending excessive velocity on C-bindings, packaging, and scaffolding before validating prompt injection dynamics, vector similarity thresholds, and tokenizer portability across Claude, Gemini, and Cursor.

## Decision Drivers
* **Velocity to Working Artifact:** Need a working MCP server connecting to Claude Desktop and Cursor in under one week.
* **Algorithmic Validation:** Need rapid experimentation with embedding backends (Ollama, fastembed, ONNX Runtime) and RRF fusion constants ($k=60$).
* **Distribution & Resource Invariants:** Production target demands a single, statically-linked binary with <5ms cold start and <30MB baseline RAM.

## Considered Options

### Option 1: Pure Go (1.24+) from Day 1
* **Pros:** Single binary output, native goroutines for worker supervision, Swiss Table maps, fast runtime.
* **Cons:** CGO overhead and cross-compilation friction when embedding SQLite with `sqlite-vec` or ONNX runtimes; slower iterative loop for tuning RAG heuristics.

### Option 2: Pure Rust from Day 1
* **Pros:** Zero-cost abstractions, direct memory control, optimal vector performance.
* **Cons:** Slower compilation times, high scaffolding ceremony for fast prototyping of MCP tool definitions and dynamic schema evolution.

### Option 3: Two-Phase Approach (Python + `uv` for V1 Prototype -> Go 1.24+ for V2 Production Daemon)
* **Pros:**
  * **V1 (Python 3.12 + `uv`):** Maximum iteration speed. First-class libraries for MCP (`mcp` SDK), fast SQLite integration with vector extensions (`sqlite-vec`), quick embedding generation, and interactive CLI. Proves product value and verifies retrieval accuracy immediately.
  * **V2 (Go 1.24+):** Once schemas, tools, and retrieval weights are hardened, port the verified engine to a compiled, standalone daemon implementing the full systems architecture (Swiss Tables, Unix Domain Socket daemon, Erlang-style supervisor trees).
* **Cons:** Requires a rewrite phase from Python to Go once the prototype is validated.

## Decision
We adopt **Option 3: Two-Phase Implementation Stack**.
1. **Phase 1 (V1 Validation Engine):** Implemented in **Python 3.12+** using **`uv`** for dependency isolation and instant execution. Focuses on:
   * SQLite WAL storage with FTS5 and `sqlite-vec`.
   * Hybrid retrieval (BM25 + cosine similarity) fused via Reciprocal Rank Fusion (RRF).
   * Local embeddings via Ollama HTTP client with local ONNX/fastembed fallback.
   * Standard MCP server interface over Stdio for Claude Desktop and Cursor.
   * Living Markdown mirror (`BATTERY.md`) auto-syncing.
2. **Phase 2 (V2 Systems Engine):** Hardened as a single-binary **Go 1.24+** daemon running over a secure Unix Domain Socket (`battery.sock`).

## Consequences

### Positive
* Delivers an end-to-end usable MCP memory tool immediately.
* Allows empirical testing of retrieval recall and latency before committing to binary ABIs.
* Clean separation of concerns: algorithmic design first, systems optimization second.

### Negative
* Logic will need to be ported to Go for V2. (Mitigated by keeping V1 codebase lean, modular, and heavily unit-tested).
