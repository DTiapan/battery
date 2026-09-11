# 🔋 Battery Context Engine — Retrieval Benchmark Results

**Date:** 2026-09-11
**Evaluation Queries:** 15
**Corpus Size:** 15 items

## Overall Retrieval Performance

| Retrieval Strategy | Hit@1 | Hit@3 | Hit@5 | MRR | Avg Latency | p50 Latency |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **BM25 (FTS5)** | **60.0%** | **66.7%** | **66.7%** | **0.6333** | 0.6ms | 0.5ms |
| **Vector (sqlite-vec)** | **86.7%** | **93.3%** | **100.0%** | **0.9022** | 16.7ms | 15.9ms |
| **Battery Hybrid (RRF)** | **73.3%** | **93.3%** | **100.0%** | **0.8389** | 16.9ms | 16.6ms |

## Performance by Query Intent

| Query Intent | Method | Hit@1 | Hit@3 | MRR |
| :--- | :--- | :---: | :---: | :---: |
| Exact Keyword | BM25 (FTS5) | 80% | 100% | 0.900 |
| Exact Keyword | Vector (sqlite-vec) | 100% | 100% | 1.000 |
| Exact Keyword | Battery Hybrid (RRF) | 80% | 100% | 0.900 |
| Hybrid Technical | BM25 (FTS5) | 40% | 40% | 0.400 |
| Hybrid Technical | Vector (sqlite-vec) | 80% | 100% | 0.867 |
| Hybrid Technical | Battery Hybrid (RRF) | 60% | 80% | 0.717 |
| Semantic Concept | BM25 (FTS5) | 60% | 60% | 0.600 |
| Semantic Concept | Vector (sqlite-vec) | 80% | 80% | 0.840 |
| Semantic Concept | Battery Hybrid (RRF) | 80% | 100% | 0.900 |
