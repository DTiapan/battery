# 🔋 Battery — Real-World Retrieval Benchmark

**Corpus:** 92 genuine engineering memories (Battery ADRs, README, docstrings, curated rules)\
**Queries:** 30 authentic developer / LLM agent queries\
**Engine:** SQLite WAL + FTS5 BM25 + sqlite-vec ONNX `all-MiniLM-L6-v2`

---

## Overall Retrieval Performance

| Retrieval Strategy | Hit@1 | Hit@3 | Hit@5 | MRR | Avg Latency | p50 Latency | p95 Latency |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **BM25 (FTS5)** | **73.3%** | **86.7%** | **86.7%** | **0.7944** | 0.7ms | 0.6ms | 1.0ms |
| **Vector (sqlite-vec)** | **76.7%** | **90.0%** | **93.3%** | **0.8289** | 14.0ms | 13.8ms | 15.8ms |
| **Battery Hybrid (RRF)** | **83.3%** | **83.3%** | **93.3%** | **0.8550** | 15.6ms | 14.4ms | 25.1ms |

## Performance by Query Intent

| Query Intent | Method | Hit@1 | Hit@3 | MRR |
| :--- | :--- | :---: | :---: | :---: |
| Exact Keyword | BM25 (FTS5) | 100% | 100% | 1.000 |
| Exact Keyword | Vector (sqlite-vec) | 90% | 100% | 0.950 |
| Exact Keyword | Battery Hybrid (RRF) | 100% | 100% | 1.000 |
| Hybrid Technical | BM25 (FTS5) | 50% | 80% | 0.650 |
| Hybrid Technical | Vector (sqlite-vec) | 80% | 100% | 0.883 |
| Hybrid Technical | Battery Hybrid (RRF) | 80% | 80% | 0.845 |
| Semantic Concept | BM25 (FTS5) | 70% | 80% | 0.733 |
| Semantic Concept | Vector (sqlite-vec) | 60% | 70% | 0.653 |
| Semantic Concept | Battery Hybrid (RRF) | 70% | 70% | 0.720 |
