# 🔋 Battery — Near-Duplicate Re-Ingest Stress Report

**Corpus:** 500 memories**Re-ingest paraphrases:** 200**Targets:** ≥ 40% duplicate row reduction; no hybrid MRR regression

---

## Summary

| Metric | Result | Target | Status |
| :--- | :---: | :---: | :---: |
| **Naive extra rows** | **200** | — | — |
| **Dedup extra rows** | **6** | ≪ naive | ✅ |
| **Duplicate row reduction** | **97.0%** | ≥ 40% | ✅ |
| **Paraphrase merge rate** | **97.0%** | — | — |
| **Baseline hybrid MRR (pre re-ingest)** | **0.8594** | — | — |
| **Naive post re-ingest hybrid MRR** | **0.8233** | — | — |
| **Dedup post re-ingest hybrid MRR** | **0.8428** | ≥ 0.8223 | ✅ |
| **MRR delta vs naive re-ingest** | **+0.0194** | ≥ -0.001 | ✅ |
