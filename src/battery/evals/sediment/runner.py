"""Run Sediment benchmark with Battery adapters registered."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from battery.evals.sediment.battery_adapter import (
    BatteryBm25Adapter,
    BatteryHybridAdapter,
    BatteryVectorAdapter,
)

SEDIMENT_PIN_FILE = (
    Path(__file__).resolve().parents[4] / "vendor" / "sediment-benchmark" / ".battery-pin"
)


def sediment_root() -> Path:
    root = Path(__file__).resolve().parents[4] / "vendor" / "sediment-benchmark"
    if not root.is_dir():
        raise FileNotFoundError(
            "vendor/sediment-benchmark not found. Run: "
            "git submodule update --init vendor/sediment-benchmark"
        )
    return root


def register_battery_adapters(sediment_run) -> None:
    """Register Battery adapters without pulling optional Sediment competitor deps."""
    sediment_run.ADAPTERS.clear()
    sediment_run.ADAPTERS["battery"] = BatteryHybridAdapter
    sediment_run.ADAPTERS["battery-bm25"] = BatteryBm25Adapter
    sediment_run.ADAPTERS["battery-vector"] = BatteryVectorAdapter

    try:
        from adapters.chromadb_baseline import ChromaDBAdapter

        sediment_run.ADAPTERS["chromadb"] = ChromaDBAdapter
    except ImportError:
        pass


def run_sediment_benchmark(
    *,
    systems: str = "battery",
    phases: str = "retrieval",
    seed: int = 42,
) -> None:
    """Execute Tier 1 comparative eval via upstream Sediment run.py."""
    root = sediment_root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    import run as sediment_run  # noqa: WPS433 — vendored harness

    def _battery_register() -> None:
        register_battery_adapters(sediment_run)

    sediment_run._register_adapters = _battery_register  # type: ignore[method-assign]

    args = argparse.Namespace(
        systems=systems,
        phases=phases,
        seed=seed,
        sediment_bin="sediment",
        letta_url="http://localhost:8283",
    )
    asyncio.run(sediment_run.main_async(args))


def main() -> None:
    parser = argparse.ArgumentParser(description="Battery × Sediment Tier 1 benchmark")
    parser.add_argument(
        "--systems",
        default="battery",
        help="Comma-separated systems (battery, battery-bm25, battery-vector, chromadb, ...)",
    )
    parser.add_argument(
        "--phases",
        default="retrieval",
        help="retrieval,temporal,dedup,latency or all",
    )
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    run_sediment_benchmark(systems=args.systems, phases=args.phases, seed=args.seed)


if __name__ == "__main__":
    main()
