# 🔋 Battery — Cross-Tool Handoff Benchmark Report

**Scenarios:** 6 polyglot continuity cases**Target:** all pass; lineage ≥ 3 hops traceable

---

## Summary

| Metric | Result | Target | Status |
| :--- | :---: | :---: | :---: |
| **Scenarios passed** | **6/6** | all | ✅ |

---

## Scenario Results

| Scenario | Pass | Detail |
| :--- | :---: | :--- |
| **cursor-to-claude-resume** | PASS | missing_tokens=0 |
| **ingest-recall-after-switch** | PASS | results=2 |
| **lineage-three-hops** | PASS | artifact_lineage=2, file_hops=3 |
| **session-start-injection** | PASS | context_len=713 |
| **file-verification-on-export** | PASS | status=partial |
| **latest-context-reader** | PASS | present=True |
