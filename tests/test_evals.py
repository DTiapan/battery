import pytest
from battery.evals.harness import run_evaluation, load_dataset

def test_evaluation_harness_execution():
    """Validates that the evaluation harness runs end-to-end and returns benchmark metrics."""
    dataset = load_dataset()
    assert len(dataset["corpus"]) > 0
    assert len(dataset["queries"]) > 0

    results = run_evaluation(dataset=dataset, output_markdown=False, output_json=False)

    for method in ["BM25 (FTS5)", "Vector (sqlite-vec)", "Battery Hybrid (RRF)"]:
        assert method in results
        m_data = results[method]
        assert 0.0 <= m_data["Hit@1"] <= 1.0
        assert 0.0 <= m_data["Hit@3"] <= 1.0
        assert 0.0 <= m_data["Hit@5"] <= 1.0
        assert 0.0 <= m_data["MRR"] <= 1.0
        assert m_data["Latency_Avg_ms"] > 0.0
