"""local-memory-mcp adapter for Sediment Tier 1 comparative eval."""

from __future__ import annotations

import shutil
from typing import Any

from battery.evals.sediment.mcp_stdio import (
    McpStdioClient,
    comparative_workspace,
    parse_tool_payload,
)

LOCAL_MEMORY_PACKAGE = "@studiomeyer/local-memory-mcp@1.0.7"

LEARN_CATEGORY_MAP: dict[str, str] = {
    "architecture": "architecture",
    "code_patterns": "pattern",
    "project_facts": "architecture",
    "user_preferences": "workflow",
    "troubleshooting": "insight",
    "cross_project": "research",
}


def _map_learn_category(metadata: dict | None) -> str:
    if not metadata:
        return "insight"
    category = metadata.get("category")
    if isinstance(category, str):
        return LEARN_CATEGORY_MAP.get(category, "insight")
    return "insight"


def _extract_rows(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    data = payload.get("data", payload)
    if not isinstance(data, dict):
        return []
    rows = data.get("results")
    if isinstance(rows, list):
        return [row for row in rows if isinstance(row, dict)]
    return []


class LocalMemoryMcpAdapter:
    """local-memory-mcp FTS search via memory_search (C2)."""

    name = "local-memory-mcp"

    def __init__(self, workspace: Any = None) -> None:
        self._workspace = workspace or comparative_workspace("local-memory-mcp")
        self._db_path = self._workspace / "memory.sqlite"
        self._client: McpStdioClient | None = None
        self._store_count = 0

    def _build_client(self) -> McpStdioClient:
        self._workspace.mkdir(parents=True, exist_ok=True)
        return McpStdioClient(
            command="npx",
            args=["-y", LOCAL_MEMORY_PACKAGE],
            env={"MEMORY_DB_PATH": str(self._db_path)},
        )

    async def setup(self) -> None:
        self._client = self._build_client()
        await self._client.connect()

    async def teardown(self) -> None:
        if self._client is not None:
            await self._client.disconnect()
            self._client = None
        if self._workspace.exists():
            shutil.rmtree(self._workspace, ignore_errors=True)

    async def reset(self) -> None:
        if self._client is not None:
            await self._client.disconnect()
            self._client = None
        if self._workspace.exists():
            shutil.rmtree(self._workspace, ignore_errors=True)
        self._store_count = 0
        self._client = self._build_client()
        await self._client.connect()

    async def store(self, item) -> None:
        assert self._client is not None
        category = _map_learn_category(item.metadata)
        text = await self._client.call_tool(
            "memory_learn",
            {
                "category": category,
                "content": item.content,
                "project": "sediment-bench",
                "tags": [item.metadata["category"]] if item.metadata and item.metadata.get("category") else [],
                "memoryType": "semantic",
            },
        )
        payload = parse_tool_payload(text)
        if isinstance(payload, dict) and payload.get("success") is False:
            raise RuntimeError(payload.get("error", "memory_learn failed"))
        self._store_count += 1

    async def recall(self, query: str, limit: int = 5) -> list:
        from adapters.base import RecallResult

        assert self._client is not None
        text = await self._client.call_tool(
            "memory_search",
            {"query": query, "limit": limit},
        )
        payload = parse_tool_payload(text)
        if isinstance(payload, dict) and payload.get("success") is False:
            return []

        results: list[RecallResult] = []
        for row in _extract_rows(payload):
            content = row.get("body") or row.get("content") or row.get("decision") or ""
            if not content and row.get("title"):
                content = str(row["title"])
            content = str(content).strip()
            if not content:
                continue
            score = row.get("rank")
            results.append(
                RecallResult(
                    id=str(row.get("id", "")),
                    content=content,
                    score=float(score) if score is not None else None,
                )
            )
        return results[:limit]

    async def count(self) -> int:
        return self._store_count
