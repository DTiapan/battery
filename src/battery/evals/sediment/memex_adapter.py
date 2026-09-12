"""memex MCP adapter for Sediment Tier 1 comparative eval."""

from __future__ import annotations

import re
import shutil
from typing import Any

from battery.evals.sediment.mcp_stdio import (
    McpStdioClient,
    comparative_workspace,
    parse_tool_payload,
    resolve_memex_bin,
)

MEMEX_TYPE_MAP: dict[str, str] = {
    "architecture": "decision",
    "code_patterns": "procedure",
    "project_facts": "fact",
    "user_preferences": "preference",
    "troubleshooting": "note",
    "cross_project": "fact",
}


def _map_memex_type(metadata: dict | None) -> str:
    if not metadata:
        return "fact"
    category = metadata.get("category")
    if isinstance(category, str):
        return MEMEX_TYPE_MAP.get(category, "fact")
    return "fact"


def _parse_memex_recall(text: str) -> list[dict[str, Any]]:
    """Parse memex recall text into {id, content} dicts."""
    payload = parse_tool_payload(text)
    if isinstance(payload, list):
        return [_normalize_memex_item(item) for item in payload if _normalize_memex_item(item)]
    if isinstance(payload, dict):
        for key in ("results", "memories", "items"):
            items = payload.get(key)
            if isinstance(items, list):
                return [_normalize_memex_item(item) for item in items if _normalize_memex_item(item)]
        if "content" in payload:
            normalized = _normalize_memex_item(payload)
            return [normalized] if normalized else []

    items: list[dict[str, Any]] = []
    for block in re.split(r"\n(?=\d+\.\s|\- \[id=)", text.strip()):
        block = block.strip()
        if not block:
            continue
        mem_id_match = re.search(r"\bid[=:]?\s*([A-Za-z0-9_-]+)", block, re.I)
        content = re.sub(r"^\d+\.\s*", "", block)
        content = re.sub(r"^\-?\s*\[id=[^\]]+\]\s*", "", content, flags=re.I)
        content = re.sub(r"^\s*content:\s*", "", content, flags=re.I).strip()
        if content:
            items.append({"id": mem_id_match.group(1) if mem_id_match else "", "content": content})
    return items


def _normalize_memex_item(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {}
    content = item.get("content") or item.get("text") or item.get("memory") or ""
    if not content:
        return {}
    return {"id": str(item.get("id", "")), "content": str(content).strip()}


class MemexAdapter:
    """memex keyword recall (C1)."""

    name = "memex"

    def __init__(self, *, hybrid: bool = False, workspace: Any = None) -> None:
        self._hybrid = hybrid
        self.name = "memex-hybrid" if hybrid else "memex"
        self._workspace = workspace or comparative_workspace(self.name)
        self._client: McpStdioClient | None = None
        self._store_count = 0

    def _build_client(self) -> McpStdioClient:
        env = {
            "MEMEX_DIR": str(self._workspace),
            "MEMEX_USER_ID": "sediment-bench",
        }
        if self._hybrid:
            env["MEMEX_HYBRID"] = "1"
        return McpStdioClient(
            command=resolve_memex_bin(),
            args=["serve"],
            env=env,
        )

    async def setup(self) -> None:
        self._workspace.mkdir(parents=True, exist_ok=True)
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
        self._workspace.mkdir(parents=True, exist_ok=True)
        self._store_count = 0
        self._client = self._build_client()
        await self._client.connect()

    async def store(self, item) -> None:
        assert self._client is not None
        args = {
            "content": item.content,
            "type": _map_memex_type(item.metadata),
            "user_id": "sediment-bench",
        }
        if item.metadata and item.metadata.get("category"):
            args["tags"] = [str(item.metadata["category"])]
        await self._client.call_tool("remember", args)
        self._store_count += 1

    async def recall(self, query: str, limit: int = 5) -> list:
        from adapters.base import RecallResult

        assert self._client is not None
        text = await self._client.call_tool(
            "recall",
            {"query": query, "limit": limit, "user_id": "sediment-bench"},
        )
        parsed = _parse_memex_recall(text)
        results: list[RecallResult] = []
        for entry in parsed[:limit]:
            results.append(
                RecallResult(
                    id=entry.get("id") or "",
                    content=entry["content"],
                    score=None,
                )
            )
        return results

    async def count(self) -> int:
        return self._store_count


class MemexHybridAdapter(MemexAdapter):
    def __init__(self, workspace: Any = None) -> None:
        super().__init__(hybrid=True, workspace=workspace)
