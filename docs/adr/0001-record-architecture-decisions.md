# ADR 0001: Record Architecture Decisions

## Status
Accepted

## Date
2026-09-11

## Context
We are designing and building the **Battery Context Engine** ("Battery-Pack Memory"), a local-first, low-latency, swappable memory substrate designed to decouple stateful agent memory from stateless LLM compute.

To prevent architectural drift, ensure cross-model portability, and maintain a clear audit trail of why specific systems primitives (such as Swiss Tables, W-TinyLFU, Merkle DAGs, Roaring Bitmaps, and SQLite extensions) are borrowed or discarded, we need a standardized method for recording architectural decisions.

## Decision Drivers
* Need for clear historical rationale behind systems engineering choices.
* Need to distinguish between exploratory brainstorming and binding technical invariants.
* Need to ensure all contributors and AI agent sessions adhere to agreed architectural boundaries.

## Considered Options
* **Option 1: Informal markdown notes in repository root** (e.g., ad-hoc sections in `BATTERY_MASTER.md`).
* **Option 2: Architecture Decision Records (ADRs) in `docs/adr/`** following the Michael Nygard / MADR standard.
* **Option 3: External wiki / issue tracker.**

## Decision
We will use **Architecture Decision Records (ADRs)** stored in `docs/adr/` numbered sequentially (`0001-*.md`, `0002-*.md`).

Each ADR will document:
1. **Status:** Proposed, Accepted, Deprecated, Superseded.
2. **Context & Problem Statement.**
3. **Decision Drivers.**
4. **Considered Options with Pros/Cons.**
5. **Decision & Rationale.**
6. **Consequences (Positive, Negative, Risks & Mitigations).**

## Consequences

### Positive
* Technical choices are formally reasoned, peer-reviewed, and permanent.
* Decisions can be linked, referenced, and superseded without rewriting history.
* Agent sessions have clear guidance on immutable architectural boundaries.

### Negative
* Slight overhead in creating and maintaining ADR files for major decisions.
