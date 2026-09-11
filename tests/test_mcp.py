from pathlib import Path

import pytest

from battery.mcp_server import create_mcp_server


@pytest.mark.anyio
async def test_mcp_server_registration(tmp_path: Path):
    db_path = tmp_path / "test_battery.db"
    md_path = tmp_path / "BATTERY.md"

    server = create_mcp_server(db_path=db_path, md_path=md_path)
    assert server.name == "battery"

    tools = await server.list_tools()
    tool_names = [t.name for t in tools]
    assert "recall_memory" in tool_names
    assert "save_memory" in tool_names
    assert "forget_memory" in tool_names
    assert "list_memories" in tool_names

    resources = await server.list_resources()
    resource_uris = [r.uri for r in resources]
    assert "battery://context" in resource_uris
    assert "battery://rules" in resource_uris

    prompts = await server.list_prompts()
    prompt_names = [p.name for p in prompts]
    assert "battery-context" in prompt_names


@pytest.mark.anyio
async def test_mcp_tools_lifecycle(tmp_path: Path):
    db_path = tmp_path / "test_battery.db"
    md_path = tmp_path / "BATTERY.md"

    server = create_mcp_server(db_path=db_path, md_path=md_path)

    # 1. Save memory via MCP tool
    res = await server.call_tool(
        "save_memory",
        {
            "content": "All commits must follow Conventional Commits specification",
            "category": "rule",
            "importance": 1.0,
        },
    )
    assert not res.is_error
    saved = res.structured_content["result"]
    assert saved["status"] == "created"
    mem_id = saved["id"]

    # 2. List memories
    list_res = await server.call_tool("list_memories", {"category": "rule"})
    memories = list_res.structured_content["result"]
    assert len(memories) == 1
    assert memories[0]["id"] == mem_id

    # 3. Recall memory via hybrid search
    recall_res = await server.call_tool("recall_memory", {"query": "Conventional Commits"})
    matches = recall_res.structured_content["result"]
    assert len(matches) == 1
    assert matches[0]["id"] == mem_id

    # 4. Forget memory (tombstone)
    forget_res = await server.call_tool("forget_memory", {"memory_id": mem_id})
    assert forget_res.structured_content["result"]["status"] == "forgotten"

    # 5. Recall again - should no longer appear
    recall_after = await server.call_tool("recall_memory", {"query": "Conventional Commits"})
    assert len(recall_after.structured_content["result"]) == 0


@pytest.mark.anyio
async def test_mcp_resources(tmp_path: Path):
    db_path = tmp_path / "test_battery.db"
    md_path = tmp_path / "BATTERY.md"

    server = create_mcp_server(db_path=db_path, md_path=md_path)

    # Empty database resource reads
    ctx_res_empty = await server.read_resource("battery://context")
    assert "No memories recorded yet" in ctx_res_empty[0].content

    rules_res_empty = await server.read_resource("battery://rules")
    assert "No active rules found" in rules_res_empty[0].content

    # Populate database with distinct categories
    await server.call_tool(
        "save_memory",
        {"content": "Always run ruff check before commit", "category": "rule", "importance": 1.0},
    )
    await server.call_tool(
        "save_memory",
        {
            "content": "Use SQLite WAL mode and FTS5 triggers",
            "category": "decision",
            "importance": 0.9,
        },
    )
    await server.call_tool(
        "save_memory",
        {"content": "Prefer short functions under 50 lines", "category": "preference"},
    )

    # Read battery://context
    ctx_res = await server.read_resource("battery://context")
    content = ctx_res[0].content
    assert "# Battery Sovereign Context" in content
    assert "## Active Rules & Constraints" in content
    assert "Always run ruff check" in content
    assert "## Architectural Decisions" in content
    assert "Use SQLite WAL mode" in content
    assert "## User Preferences & Workflow Habits" in content
    assert "Prefer short functions" in content

    # Read battery://rules
    rules_res = await server.read_resource("battery://rules")
    rules_content = rules_res[0].content
    assert "# Battery Active Rules & Constraints" in rules_content
    assert "Always run ruff check" in rules_content
    # Architectural decisions must not leak into battery://rules
    assert "Use SQLite WAL mode" not in rules_content


@pytest.mark.anyio
async def test_mcp_prompt_battery_context(tmp_path: Path):
    db_path = tmp_path / "test_battery.db"
    md_path = tmp_path / "BATTERY.md"

    server = create_mcp_server(db_path=db_path, md_path=md_path)

    await server.call_tool(
        "save_memory",
        {"content": "Strict type hints required across all modules", "category": "rule"},
    )
    await server.call_tool(
        "save_memory",
        {
            "content": "FastMCP Stdio transport selected for Claude Desktop integration",
            "category": "decision",
        },
    )

    # Prompt without task
    prompt_result = await server.get_prompt("battery-context", {})
    text = prompt_result.messages[0].content.text
    assert "Battery Sovereign Context Engine" in text
    assert "Strict type hints required" in text
    assert "FastMCP Stdio transport" in text

    # Prompt with task
    prompt_task = await server.get_prompt("battery-context", {"task": "Type annotations in Python"})
    task_text = prompt_task.messages[0].content.text
    assert "Task-Relevant Memories for" in task_text
    assert "Strict type hints" in task_text
