# Battery — Agent Working Agreement

> North star: **solve real user pain** (session amnesia, context rot, tool switch, machine migration) — not feature sprawl.

## Phase discipline (one phase → one skill)

| Phase | Read first | Skill |
|-------|------------|--------|
| Problem / priority | `docs/roadmap/PRODUCT_ROADMAP.md` | `.agents/skills/product-manager-toolkit` |
| Shape / explore | `docs/adr/`, `docs/design/` | `.agents/skills/brainstorming` |
| Spec before code | New ADR draft | `.agents/skills/spec-driven-development` |
| Domain / terms | ADR + this file | `.agents/skills/domain-modeling` |
| Module design | Similar modules in `src/battery/` | `.agents/skills/codebase-design` |
| Implement | Approved ADR + ticket | `.agents/skills/implement` |
| Debug / regressions | Failing test or eval | `~/.agents/skills/diagnose` (global) |
| Review | Before merge | `~/.agents/skills/code-review` (global) |
| Context setup | Session start | `.agents/skills/context-engineering` |

**Do not** stack overlapping skills in one turn. **Do not** skip ADRs/roadmap for greenfield features.

## Scratchpad (thinking out loud)

- **Active hypotheses:** [`docs/scratchpad/ACTIVE.md`](docs/scratchpad/ACTIVE.md)
- Promote stable decisions → ADR (`docs/adr/`)
- Promote shipped work → roadmap (`docs/roadmap/PRODUCT_ROADMAP.md`)

## Canonical docs (always ground here)

1. [`docs/adr/README.md`](docs/adr/README.md) — architecture decisions
2. [`docs/roadmap/PRODUCT_ROADMAP.md`](docs/roadmap/PRODUCT_ROADMAP.md) — priorities
3. [`docs/design/battery-master-spec.md`](docs/design/battery-master-spec.md) — system spec
4. [`docs/design/cross-verification-audit.md`](docs/design/cross-verification-audit.md) — assumption ledger

## Memory model (ADR-0007)

| Tier | Categories | Inject by default? |
|------|------------|--------------------|
| Stable semantic | rule, decision, preference, general | Yes |
| Event episodic | episodic | No — handoff/search |
| Raw chat (future) | chunked episodic | Opt-in only |

## Portability

- **Team:** commit `BATTERY.md` to git
- **Individual:** `battery profile export` / `battery profile import`
- **Models:** ONNX weights not in bundle (~90MB re-download)

## Project skills (`.agents/skills/`)

Installed for this repo: product-manager-toolkit, roadmap-communicator, architecture-decision-records, hybrid-search-implementation, context-engineering, spec-driven-development, brainstorming, domain-modeling, implement, codebase-design, documentation-and-adrs, and others.

Global Matt skills remain in `~/.agents/skills/` per `dev-phase-skills` cursor rule.
