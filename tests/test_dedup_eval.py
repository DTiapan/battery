"""Tests for the near-duplicate re-ingest stress benchmark."""

from battery.evals.dedup_stress_harness import (
    DUP_REDUCTION_TARGET,
    run_dedup_stress_benchmark,
)


def test_dedup_stress_benchmark_passes_targets():
    summary = run_dedup_stress_benchmark(scale=100, output_markdown=False)
    assert summary["reduction_pass"] is True
    assert summary["duplicate_reduction_rate"] >= DUP_REDUCTION_TARGET
    assert summary["mrr_pass"] is True
    assert summary["all_passed"] is True
