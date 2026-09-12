# Scratchpad — Active Thinking

> **Purpose:** Working hypotheses and open questions **before** they become ADRs or roadmap items.  
> **Rule:** When a decision sticks, move it to `docs/adr/` and delete or shorten the entry here.

**Last updated:** 2026-09-12

---

## Current focus

**Impact over features** — v0.5.0 ships Sprint C evals + NOW-3 adoption. Next: user interviews (roadmap validation debt).

| Priority | What | Why (impact) |
|----------|------|--------------|
| 1 | ~~v0.5.0 release~~ | Sprint C + adaptive RRF + onboard path |
| 2 | **5 user interviews** | Roadmap confidence debt; validate model-switch / rot pain |
| 3 | **NEXT-4 session log ingestion** | Optional collector — after adoption proof |

Research paper: **LATER** — gates in [`PRODUCT_ROADMAP.md` §8](../roadmap/PRODUCT_ROADMAP.md). Not a build target until product proof + comparative eval exist.

---

## Recently completed

- **v0.5.0** — `battery onboard`, doctor MCP resource + recall smoke checks, Sprint C eval harnesses
- **Sprint A+B** — `IMPROVEMENT_SCORECARD.md`, AGENTS.md ship gate, adaptive RRF, 2 Hit@0 corpus fixes (real-world MRR **0.9083**)
- **v0.4.1** — profile export/import, git post-commit, ADR-0007
- **v0.3.x** — handoff, near-dedup

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
| Semantic near-dedup (≥0.88) reduces row bloat without MRR regression | Stress re-ingest eval (Sprint C) |
| Episodic should never near-dedup | Validated in v0.3.1 tests |
| Auto-capture without rot invalidation makes P2 worse | Rot benchmark suite (Sprint C) |

---

## Decisions promoted recently

- ADR-0007 tiered memory + profile bundles
- Measurement-first ship gate (scorecard row required)
- Research publication = long-term goal with explicit gates (roadmap §8), not near-term coding target

---

## Next build candidates (impact order)

1. ~~Retrieval quality pass (500-item hybrid MRR)~~ — v0.4.2
2. ~~Rot eval suite~~ — `battery eval --rot` (6/6 pass)
3. ~~Handoff scenario eval~~ — `battery eval --handoff` (6/6 pass)
4. ~~Dedup re-ingest stress~~ — `battery eval --dedup-stress` (97% dup reduction, MRR beats naive)
5. ~~NOW-3 adoption path~~ — `battery onboard` + `doctor --adoption` resource/recall checks
