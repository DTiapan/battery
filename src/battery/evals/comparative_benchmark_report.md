# Comparative Retrieval Benchmark — Tier 1 (Sediment)

**Generated:** 2026-09-12 08:42 UTC
**Battery:** v0.5.0
**Sediment harness:** `49ab23a245564111f9cc147fbb8e82885ffad7d6` (see docs/evals/SEDIMENT_PIN.md)
**memex:** 0.6.0
**local-memory-mcp:** @studiomeyer/local-memory-mcp@1.0.7
**Node:** v26.8.1 · **Go:** go version go1.27.1 darwin/arm64
**Host:** Darwin arm64 · Python 3.11.7
**Dataset:** 1,000 memories · 200 queries · seed 42

## Retrieval (primary)

| System | MRR | Recall@5 | Recall@1 | nDCG@5 | Store p95 ms | Recall p95 ms | Stored |
|--------|----:|---------:|---------:|-------:|-------------:|--------------:|-------:|
| battery | 0.609 | 0.790 | 0.470 | 0.599 | 12.7 | 15.2 | 998 |
| chromadb | 0.611 | 0.785 | 0.475 | 0.602 | 1474.3 | 1357.9 | 994 |
| memex | 0.512 | 0.635 | 0.425 | 0.498 | 4.2 | 7.3 | 1000 |
| memex-hybrid | 0.423 | 0.580 | 0.315 | 0.419 | 4.1 | 13.9 | 1000 |
| local-memory-mcp | 0.457 | 0.600 | 0.365 | 0.441 | 2.8 | 2.2 | 1000 |

## Battery MRR by category (G2d)

| Category | MRR |
|----------|----:|
| architecture | 0.562 |
| code_patterns | 0.713 |
| cross_project | 0.472 |
| project_facts | 0.592 |
| troubleshooting | 0.627 |
| user_preferences | 0.679 |

## Battery MRR by difficulty (G2d)

| Difficulty | MRR |
|------------|----:|
| easy | 0.886 |
| hard | 0.382 |
| medium | 0.584 |

## Launch gates (G2)

- [x] **G2a:** Battery MRR ≥ max(memex, local-memory-mcp) — Battery MRR 0.609 vs max competitor memex 0.512
- [x] **G2b:** Battery Recall@5 ≥ ChromaDB — Battery Recall@5 0.790 vs ChromaDB 0.785
- [x] **G2c:** Zero ingest failures — store_errors=0; 2 memories skipped by content-hash dedup (998/1000 stored) — documented exclusion, queries unaffected
- [x] **G2d:** Losses documented by category/difficulty — weakest category: cross_project MRR 0.472; weakest difficulty: hard MRR 0.382

## Notes

- Scores are only comparable within this harness run (same corpus + queries).
- Competitors use default adapter configs (memex keyword; memex-hybrid with `MEMEX_HYBRID=1`).
- Battery hybrid uses adaptive RRF with `verify=False` (rot is a separate eval).
- ChromaDB baseline had 6 ONNX store errors (994/1000 stored); scores are indicative only.
- Systems marked SKIPPED were not run (missing binary or install failure).