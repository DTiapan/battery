# 🔋 Battery — Real-World Retrieval Benchmark

**Corpus:** 92 genuine engineering memories (Battery ADRs, README, docstrings, curated rules)\
**Queries:** 30 authentic developer / LLM agent queries\
**Engine:** SQLite WAL + FTS5 BM25 + sqlite-vec ONNX `all-MiniLM-L6-v2`

---

## Overall Retrieval Performance

| Retrieval Strategy | Hit@1 | Hit@3 | Hit@5 | MRR | Avg Latency | p50 Latency | p95 Latency |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **BM25 (FTS5)** | **80.0%** | **93.3%** | **93.3%** | **0.8556** | 1.0ms | 0.6ms | 2.8ms |
| **Vector (sqlite-vec)** | **83.3%** | **96.7%** | **96.7%** | **0.8889** | 28.3ms | 28.3ms | 56.2ms |
| **Battery Hybrid (RRF)** | **86.7%** | **90.0%** | **100.0%** | **0.9083** | 29.1ms | 25.3ms | 77.1ms |

## Performance by Query Intent

| Query Intent | Method | Hit@1 | Hit@3 | MRR |
| :--- | :--- | :---: | :---: | :---: |
| Exact Keyword | BM25 (FTS5) | 100% | 100% | 1.000 |
| Exact Keyword | Vector (sqlite-vec) | 90% | 100% | 0.950 |
| Exact Keyword | Battery Hybrid (RRF) | 100% | 100% | 1.000 |
| Hybrid Technical | BM25 (FTS5) | 50% | 80% | 0.633 |
| Hybrid Technical | Vector (sqlite-vec) | 80% | 100% | 0.883 |
| Hybrid Technical | Battery Hybrid (RRF) | 70% | 80% | 0.800 |
| Semantic Concept | BM25 (FTS5) | 90% | 100% | 0.933 |
| Semantic Concept | Vector (sqlite-vec) | 80% | 90% | 0.833 |
| Semantic Concept | Battery Hybrid (RRF) | 90% | 90% | 0.925 |
