"""Tests for the cross-tool handoff scenario benchmark."""

from battery.evals.handoff_harness import HANDOFF_SCENARIOS, run_handoff_benchmark


def test_handoff_benchmark_all_scenarios_pass():
    summary = run_handoff_benchmark(output_markdown=False)
    assert summary["total_scenarios"] == len(HANDOFF_SCENARIOS)
    assert summary["passed_scenarios"] == summary["total_scenarios"]
    assert summary["all_passed"] is True
