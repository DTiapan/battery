import asyncio
import sys
from pathlib import Path

SEDIMENT_ROOT = Path(__file__).resolve().parents[1] / "vendor" / "sediment-benchmark"
if SEDIMENT_ROOT.is_dir() and str(SEDIMENT_ROOT) not in sys.path:
    sys.path.insert(0, str(SEDIMENT_ROOT))

from adapters.base import MemoryItem  # noqa: E402

from battery.evals.sediment.battery_adapter import BatteryHybridAdapter  # noqa: E402


async def _run_adapter_smoke(workspace: Path) -> None:
    adapter = BatteryHybridAdapter(workspace=workspace)
    await adapter.setup()
    await adapter.reset()

    await adapter.store(
        MemoryItem(
            id="mem_0001",
            content="Use SQLite WAL mode with FTS5 and sqlite-vec for hybrid storage.",
            metadata={"category": "architecture"},
        )
    )
    await adapter.store(
        MemoryItem(
            id="mem_0002",
            content="Prefer explicit LIMIT clauses on all production SQL queries.",
            metadata={"category": "code_patterns"},
        )
    )

    assert await adapter.count() == 2

    results = await adapter.recall("hybrid storage sqlite vec", limit=5)
    assert results
    assert any("WAL" in r.content for r in results)

    await adapter.teardown()


def test_battery_sediment_adapter_store_and_recall(tmp_path):
    asyncio.run(_run_adapter_smoke(tmp_path / "bench"))
