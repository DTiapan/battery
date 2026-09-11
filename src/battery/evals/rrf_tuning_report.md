# ⚙️ Battery RRF Parameter Tuning Report

**Evaluation Corpus:** 92 real-world engineering memories (Battery ADRs, README, docstrings, curated rules)\
**Evaluation Queries:** 30 authentic developer and LLM agent queries\
**Grid Sweep:** 6 k values × 5 weight combinations = 30 combinations tested

---

## Optimal Configuration Found

| Parameter | Default (k=60) | **Optimal (tuned)** |
| :--- | :---: | :---: |
| **k (RRF smoothing constant)** | 60 | **5** |
| **text_weight (BM25)** | 0.5 | **0.5** |
| **vec_weight (Vector)** | 0.5 | **0.5** |
| **Hit@1** | — | **83.3%** |
| **Hit@3** | — | **83.3%** |
| **MRR** | — | **0.8583** |

---

## Top-10 RRF Configurations (by MRR)

| Rank | k | text_w | vec_w | Hit@1 | Hit@3 | MRR | p50 ms |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| 1 ⭐ | 5 | 0.5 | 0.5 | 83.3% | 83.3% | 0.8583 | 14.1ms |
| 2 | 10 | 0.5 | 0.5 | 83.3% | 83.3% | 0.8567 | 14.1ms |
| 3 | 20 | 0.5 | 0.5 | 83.3% | 83.3% | 0.8550 | 14.8ms |
| 4 | 30 | 0.5 | 0.5 | 83.3% | 83.3% | 0.8550 | 14.3ms |
| 5 | 40 | 0.5 | 0.5 | 83.3% | 83.3% | 0.8550 | 14.5ms |
| 6 | 60 | 0.5 | 0.5 | 83.3% | 83.3% | 0.8550 | 13.8ms |
| 7 | 5 | 0.4 | 0.6 | 80.0% | 86.7% | 0.8428 | 14.7ms |
| 8 | 10 | 0.4 | 0.6 | 80.0% | 86.7% | 0.8428 | 14.3ms |
| 9 | 20 | 0.4 | 0.6 | 80.0% | 83.3% | 0.8400 | 14.4ms |
| 10 | 30 | 0.4 | 0.6 | 80.0% | 83.3% | 0.8400 | 14.4ms |

---

## Baseline Comparison

| Method | Hit@1 | Hit@3 | MRR |
| :--- | :---: | :---: | :---: |
| BM25 (FTS5) | 73.3% | 86.7% | 0.7944 |
| Vector (sqlite-vec) | 76.7% | 90.0% | 0.8289 |
| **Battery Hybrid (k=5, tw=0.5)** | **83.3%** | **83.3%** | **0.8583** |
