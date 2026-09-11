from battery.evals.harness import load_dataset, run_evaluation


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


def test_stress_benchmark_execution():
    """Validates that the scaled stress test harness executes cleanly without disk leaks."""
    from battery.evals.stress_test import run_stress_benchmark

    summary = run_stress_benchmark(scale=10, output_markdown=False)
    assert summary["scale"] == 10
    assert summary["ingest_throughput_items_sec"] > 0
    assert summary["db_size_kb"] > 0
    for method in ["BM25 (FTS5)", "Vector (sqlite-vec)", "Battery Hybrid (RRF)"]:
        assert method in summary["methods"]
        assert 0.0 <= summary["methods"][method]["MRR"] <= 1.0
