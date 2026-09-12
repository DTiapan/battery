# Scratchpad — Active Thinking

> **Purpose:** Working hypotheses and open questions **before** they become ADRs or roadmap items.  
> **Rule:** When a decision sticks, move it to `docs/adr/` and delete or shorten the entry here.

**Last updated:** 2026-09-12

---

## Current focus

**Profile portability (ADR-0007)** — users need to move `battery.db` to a new machine without manual `cp` guesswork.

- Shipped: `battery profile export/import/inspect` with checksum-verified `.battery-bundle`
- Team path unchanged: `BATTERY.md` in git + `battery sync`
- ONNX models excluded from bundle (re-download on first embed)

---

## Open questions

1. **Episodic decay** — when do old checkpoints fade? (Ebbinghaus λ tuning deferred; needs eval)
2. **MacPaw `.mem` adapter** — worth interoperability layer or stay battery-native for now?
3. **MCP export tools** — CLI sufficient for v0.4 or agents need `export_profile` tool?
4. **Everyday user persona** — bundle UX is still CLI; GUI/export wizard is LATER

---

## Hypotheses under test

| Hypothesis | Validation |
|------------|------------|
| Developers migrate machines ≥1×/year and hit `~/.battery` friction | 5–8 interviews (roadmap validation debt) |
| Semantic near-dedup (≥0.88) reduces row bloat without MRR regression | Stress re-ingest eval (TODO) |
| Episodic should never near-dedup | Validated in v0.3.1 tests |

---

## Decisions promoted recently

- ADR-0007 tiered memory + profile bundles
- Five categories kept; tiered **behavior** not new enums
- Scratchpad + AGENTS.md for phase discipline

---

## Next build candidates (roadmap order)

1. ~~Git post-commit episodic capture (NEXT-3)~~ — shipped v0.4.1
2. Retrieval quality pass (500-item hybrid MRR)
3. Session log ingestion opt-in (NEXT-4)
