"""Shared MCP stdio client helpers for comparative eval adapters."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def comparative_workspace(name: str) -> Path:
    return repo_root() / "src/battery/evals/.comparative_workspaces" / name


def parse_tool_payload(text: str) -> Any:
    """Parse MCP tool text — JSON object or plain text."""
    text = text.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


class McpStdioClient:
    """Minimal async MCP stdio subprocess wrapper."""

    def __init__(
        self,
        *,
        command: str,
        args: list[str],
        env: dict[str, str] | None = None,
    ) -> None:
        self._command = command
        self._args = args
        self._env = env or {}
        self._stdio_cm: Any = None
        self._session_cm: Any = None
        self._session: ClientSession | None = None

    @property
    def session(self) -> ClientSession:
        if self._session is None:
            raise RuntimeError("MCP session not connected — call connect() first")
        return self._session

    async def connect(self) -> None:
        server_params = StdioServerParameters(
            command=self._command,
            args=self._args,
            env={**os.environ, **self._env},
        )
        self._stdio_cm = stdio_client(server_params)
        read, write = await self._stdio_cm.__aenter__()
        self._session_cm = ClientSession(read, write)
        self._session = await self._session_cm.__aenter__()
        await self._session.initialize()

    async def disconnect(self) -> None:
        try:
            if self._session_cm is not None:
                await self._session_cm.__aexit__(None, None, None)
        finally:
            self._session_cm = None
            self._session = None
        try:
            if self._stdio_cm is not None:
                await self._stdio_cm.__aexit__(None, None, None)
        finally:
            self._stdio_cm = None

    async def call_tool(self, tool: str, arguments: dict[str, Any]) -> str:
        result = await self.session.call_tool(tool, arguments)
        if getattr(result, "is_error", False) or getattr(result, "isError", False):
            detail = result.content[0].text if result.content else "unknown error"
            raise RuntimeError(f"MCP tool {tool} failed: {detail}")
        if not result.content:
            return ""
        return result.content[0].text


def resolve_memex_bin() -> str:
    candidates = [
        os.environ.get("MEMEX_BIN"),
        shutil.which("memex"),
        str(Path.home() / "go/bin/memex"),
        str(Path.home() / ".local/bin/memex"),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).expanduser().exists():
            return str(Path(candidate).expanduser())
    raise FileNotFoundError(
        "memex binary not found. Install: go install github.com/kioie/memex/cmd/memex@v0.6.0"
    )
