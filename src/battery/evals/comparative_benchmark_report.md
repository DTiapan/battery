# Comparative Retrieval Benchmark — Tier 1 (Sediment)

**Generated:** 2026-09-12 07:46 UTC
**Harness:** sediment-benchmark (see docs/evals/SEDIMENT_PIN.md)
**Dataset:** 1,000 memories · 200 queries

## Retrieval (primary)

| System | MRR | Recall@5 | Recall@1 | nDCG@5 | Store p95 ms | Recall p95 ms | Stored |
|--------|----:|---------:|---------:|-------:|-------------:|--------------:|-------:|
| battery | 0.609 | 0.790 | 0.470 | 0.599 | 12.4 | 14.1 | 998 |
| local-memory-mcp | 0.457 | 0.600 | 0.365 | 0.441 | 3.3 | 2.1 | 1000 |

## Launch gate

- [x] G2a vs **local-memory-mcp**: Battery MRR 0.609 > 0.457 (Recall@5 0.790 > 0.600)
- [ ] G2a vs **memex**: not run (requires `go install github.com/kioie/memex/cmd/memex@v0.6.0`)
- [ ] G2b: Battery Recall@5 ≥ ChromaDB (optional baseline)
- [x] G2c: local-memory-mcp 0 ingest errors; Battery 2 exact-hash dedups (998/1000)

## Notes

- Scores are only comparable within this harness run (same corpus + queries).
- Systems marked SKIPPED were not run (missing binary or install failure).