"""Tests for the context rot benchmark harness."""

from battery.evals.rot_harness import ROT_SCENARIOS, run_rot_benchmark


def test_rot_benchmark_all_scenarios_pass():
    summary = run_rot_benchmark(output_markdown=False)
    assert summary["total_scenarios"] == len(ROT_SCENARIOS)
    assert summary["stale_recall_failures"] == 0
    assert summary["passed_scenarios"] == summary["total_scenarios"]
    assert summary["all_passed"] is True


def test_rot_benchmark_verify_latency_under_target():
    summary = run_rot_benchmark(output_markdown=False)
    assert summary["verify_latency_p95_ms"] < summary["verify_p95_target_ms"]
