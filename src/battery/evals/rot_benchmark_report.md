# 🔋 Battery — Context Rot Benchmark Report

**Scenarios:** 6 citation / prune rot cases**Target:** 0 stale-recall failures; JIT verify p95 < 10.0ms

---

## Summary

| Metric | Result | Target | Status |
| :--- | :---: | :---: | :---: |
| **Scenarios passed** | **6/6** | all | ✅ |
| **Stale-recall failures** | **0** | 0 | ✅ |
| **JIT verify p95 latency** | **0.252 ms** | < 10.0 ms | ✅ |
| **JIT verify avg latency** | **0.072 ms** | — | — |

---

## Scenario Results

| Scenario | Pass | Stale Leak | Verify (ms) | Detail |
| :--- | :---: | :---: | :---: | :--- |
| **stale-snippet-excluded** | PASS | no | 0.028 | control_unverified_includes_stale=True |
| **missing-file-excluded** | PASS | no | 0.028 | file_deleted |
| **valid-citation-recall** | PASS | no | 0.252 | found=True |
| **uncited-memory-immune** | PASS | no | 0.025 | found=True |
| **stale-yields-fresh-fallback** | PASS | no | 0.028 | fresh_found=True |
| **prune-tombstones-stale** | PASS | no | — | pruned=True, still_searchable=False |
