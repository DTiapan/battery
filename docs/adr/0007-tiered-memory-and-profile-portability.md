# ADR 0007: Tiered Memory Lifecycle and Profile Portability Bundles

## Status
Accepted

## Date
2026-09-12

## Context

Battery stores project memory in local SQLite files (`battery.db`) with a git-committable `BATTERY.md` mirror. Developers asked a practical question: **how do I move my memory to a new computer?**

Research and adjacent standards converge on the same requirement:

- [Portable Agent Memory (arXiv 2605.11032)](https://arxiv.org/html/2605.11032) — episodic/semantic/procedural envelopes with verified transfer
- [MacPaw Portable Memory](https://github.com/MacPaw/portable-memory) — local `.mem` bundles with manifest + checksums
- Battery ADR-0005 — human-readable mirror for git-native sharing
- Battery ADR-0006 — per-profile physical isolation

Today, team context travels via **`BATTERY.md` in git**, but **personal/global profiles** (`~/.battery/`) require manual directory copy with no manifest, checksums, or CLI guidance. That is a user pain point and a trust gap.

Separately, auto-capture (hooks, handoff) increases memory volume. Not all memory types should behave the same at recall or dedup time:

| Tier | Categories | Behavior |
|------|------------|----------|
| **Stable semantic** | `rule`, `decision`, `preference`, `general` | Mirror to git, near-dedup, session-start inject |
| **Event episodic** | `episodic` | Checkpoints, handoffs, commits; search on demand |
| **Raw conversational** (future) | chunked episodic | Opt-in collectors only |

## Decision Drivers

* **User-owned portability:** Memory must move across machines without vendor lock-in.
* **SQLite is already portable:** A single-file DB is the substrate; users need a **bundle UX**, not a new database.
* **Inspectability:** Bundles include manifest + SHA-256 checksums (Portable Memory pattern).
* **Tiered lifecycle:** Semantic and episodic memories must not share the same dedup/inject rules.
* **North star:** Solve developer pain (session amnesia, tool switch, machine migration) — not academic taxonomy explosion.

## Considered Options

### Option 1: Document Manual `cp ~/.battery` Only
* **Pros:** Zero implementation cost.
* **Cons:** Error-prone (WAL files, missing models dir); no checksum verification; poor everyday-user story.

### Option 2: Cloud Sync Directory
* **Pros:** Automatic multi-device sync.
* **Cons:** Violates local-first sovereignty; privacy risk if iCloud/Dropbox syncs `battery.db` unintentionally (flagged in cross-verification audit).

### Option 3: Local `.battery-bundle` Export/Import (Selected)
* **Pros:**
  * ZIP archive: `manifest.json` + `battery.db` + optional `BATTERY.md`
  * SHA-256 checksums verified on import
  * Profile-scoped: `battery profile export` / `battery profile import`
  * Aligns with Portable Memory / PAM envelope thinking without requiring full protocol adoption yet
  * ONNX model weights excluded (re-download on first embed — bundle stays small)
* **Cons:** Manual export/import step (acceptable for v0.4; auto-sync deferred).

### Option 4: Add `conversational` and `procedural` DB Enums Now
* **Pros:** Matches cognitive-science papers literally.
* **Cons:** Procedural fits `rule`/`preference` today; conversational should be opt-in chunked episodic (NEXT-4). Premature enum growth.

## Decision

We adopt **Option 3** for portability and **retain five categories with tiered lifecycle** (Option 4 rejected for now).

### 1. Tiered memory lifecycle (behavioral, not new enums)

| Category | Near-dedup on save | Default session inject | Primary portability path |
|----------|-------------------|------------------------|--------------------------|
| `rule`, `decision`, `preference`, `general` | Yes (≥0.88 cosine) | Yes (`battery://rules`, `battery://context`) | `BATTERY.md` in git + bundle |
| `episodic` | No | No (handoff/checkpoint on demand) | Bundle + search |
| Future transcript chunks | No | No (opt-in) | Bundle + search |

### 2. Profile bundle format (`battery-bundle` v1)

```text
my-profile.battery-bundle  (ZIP)
├── manifest.json          # format, profile, schema_version, checksums
├── battery.db             # SQLite WAL checkpointed at export
└── BATTERY.md             # optional mirror snapshot
```

`manifest.json` fields: `bundle_format`, `bundle_version`, `profile`, `schema_version`, `embedding_model`, `exported_at`, `checksums`, `notes`.

### 3. CLI

```bash
battery profile export [--profile NAME] --out backup.battery-bundle [--include-md]
battery profile import backup.battery-bundle [--profile NAME] [--force]
battery profile inspect backup.battery-bundle
```

### 4. Scratchpad (process, not runtime)

Working hypotheses live in `docs/scratchpad/ACTIVE.md` until promoted to ADR/roadmap. Prevents spec drift during exploration.

## Consequences

### Positive
* Directly answers machine migration pain for solo devs and consultants with isolated profiles.
* Checksum verification builds trust (Portable Memory alignment).
* Tiered lifecycle prevents episodic/session noise from polluting stable rules.
* Complements ADR-0005 git mirror (team) with ADR-0007 bundle (individual).

### Negative
* Bundles do not include ONNX weights (~90MB) — first embed on new machine triggers download.
* No automatic cross-device sync — user must re-export after changes.
* Cross-profile federated search remains future work (ADR-0006 consequence).

### Follow-ups
* Optional `.mem` adapter for MacPaw interoperability (LATER).
* Episodic TTL/decay (Ebbinghaus) — separate ADR when empirically tuned.
* MCP tools `export_profile` / `import_profile` (optional).

## References

- ADR-0005 MCP + Living Mirror
- ADR-0006 Multi-Battery Profiles
- `docs/design/cross-verification-audit.md` (privacy, async embedding assumptions)
- `docs/scratchpad/ACTIVE.md`
