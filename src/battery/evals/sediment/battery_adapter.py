"""Battery MemoryAdapter for the Sediment benchmark harness."""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path
from typing import Literal

from battery.db import get_connection, init_db, insert_memory
from battery.embeddings import embed_text
from battery.retrieval import hybrid_search, search_bm25, search_vector

SearchMode = Literal["hybrid", "bm25", "vector"]

# Sediment dataset categories → Battery memory categories
CATEGORY_MAP: dict[str, str] = {
    "architecture": "decision",
    "code_patterns": "rule",
    "project_facts": "decision",
    "user_preferences": "preference",
    "troubleshooting": "general",
    "cross_project": "general",
}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _default_workspace(mode: str) -> Path:
    return _repo_root() / "src/battery/evals/.comparative_workspaces" / f"battery-sediment-{mode}"


def _map_category(metadata: dict | None) -> str:
    if not metadata:
        return "general"
    raw = metadata.get("category")
    if isinstance(raw, str):
        return CATEGORY_MAP.get(raw, "general")
    return "general"


class BatteryAdapter:
    """Sediment-compatible adapter backed by Battery SQLite + hybrid retrieval."""

    def __init__(self, mode: SearchMode = "hybrid", workspace: Path | None = None) -> None:
        self._mode = mode
        self._workspace = workspace or _default_workspace(mode)
        self._db_path = self._workspace / "battery.db"
        self._conn = None
        self.name = {
            "hybrid": "battery",
            "bm25": "battery-bm25",
            "vector": "battery-vector",
        }[mode]

    def _require_conn(self):
        if self._conn is None:
            raise RuntimeError("Call setup() first")
        return self._conn

    async def setup(self) -> None:
        self._workspace.mkdir(parents=True, exist_ok=True)
        self._conn = get_connection(self._db_path)
        init_db(self._conn)

    async def teardown(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
        if self._workspace.exists():
            shutil.rmtree(self._workspace, ignore_errors=True)

    async def reset(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
        if self._workspace.exists():
            shutil.rmtree(self._workspace, ignore_errors=True)
        self._workspace.mkdir(parents=True, exist_ok=True)
        self._conn = get_connection(self._db_path)
        init_db(self._conn)

    async def store(self, item) -> None:
        conn = self._require_conn()
        category = _map_category(item.metadata)
        content = item.content.strip()

        def _insert() -> None:
            embedding = embed_text(content)
            insert_memory(
                conn,
                content,
                embedding,
                category=category,
                importance=1.0,
                source="sediment-bench",
                log_event=False,
                near_dedup=False,
            )

        await asyncio.to_thread(_insert)

    async def recall(self, query: str, limit: int = 5) -> list:
        from adapters.base import RecallResult

        conn = self._require_conn()

        def _search():
            if self._mode == "hybrid":
                return hybrid_search(conn, query, limit=limit, verify=False)
            if self._mode == "bm25":
                return search_bm25(conn, query, limit=limit)
            return search_vector(conn, query, limit=limit)

        rows = await asyncio.to_thread(_search)
        results: list[RecallResult] = []
        for row in rows:
            score = row.get("rrf_score")
            if score is None:
                score = row.get("score")
            results.append(
                RecallResult(
                    id=str(row["id"]),
                    content=row["content"],
                    score=float(score) if score is not None else None,
                )
            )
        return results

    async def count(self) -> int:
        conn = self._require_conn()
        row = conn.execute("SELECT COUNT(*) FROM memories WHERE is_deleted = 0").fetchone()
        return int(row[0]) if row else 0


class BatteryHybridAdapter(BatteryAdapter):
    def __init__(self, workspace: Path | None = None) -> None:
        super().__init__(mode="hybrid", workspace=workspace)


class BatteryBm25Adapter(BatteryAdapter):
    def __init__(self, workspace: Path | None = None) -> None:
        super().__init__(mode="bm25", workspace=workspace)


class BatteryVectorAdapter(BatteryAdapter):
    def __init__(self, workspace: Path | None = None) -> None:
        super().__init__(mode="vector", workspace=workspace)
