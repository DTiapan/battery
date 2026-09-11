from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp.server.mcpserver import MCPServer

from battery.config import (
    get_profile_db_path,
    get_profile_md_path,
)
from battery.db import (
    get_connection,
    init_db,
    insert_memory,
    tombstone_memory,
)
from battery.db import (
    list_memories as db_list_memories,
)
from battery.embeddings import embed_text
from battery.retrieval import hybrid_search
from battery.sync import export_battery_md


def create_mcp_server(
    db_path: Optional[Path] = None,
    md_path: Optional[Path] = None,
    profile: Optional[str] = None,
) -> MCPServer:
    """Instantiates and configures the Battery MCP server with standard tools."""
    resolved_db = db_path or get_profile_db_path(profile)
    resolved_md = md_path or get_profile_md_path(profile)
    server = MCPServer(
        name="battery",
        instructions=(
            "Battery is a local sovereign context engine. Use 'recall_memory' to search past "
            "rules, architectural decisions, and project conventions. Use 'save_memory' to persist "
            "new rules or decisions."
        ),
        version="0.1.0",
    )

    conn = get_connection(resolved_db)
    init_db(conn)

    @server.tool(
        description="Search personal context, project rules, and architectural decisions using hybrid search."
    )
    def recall_memory(
        query: str, limit: int = 5, category: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        return hybrid_search(conn, query, limit=limit, category=category)

    @server.tool(
        description="Persist a rule, architectural decision, user preference, or fact to local memory."
    )
    def save_memory(
        content: str, category: str = "general", importance: float = 1.0
    ) -> Dict[str, Any]:
        vec = embed_text(content)
        result = insert_memory(conn, content, vec, category=category, importance=importance)
        # Update living BATTERY.md mirror
        try:
            export_battery_md(conn, resolved_md)
        except Exception:
            pass
        return result

    @server.tool(description="Tombstone a stored memory by ID so it no longer matches queries.")
    def forget_memory(memory_id: int) -> Dict[str, Any]:
        success = tombstone_memory(conn, memory_id)
        if success:
            try:
                export_battery_md(conn, resolved_md)
            except Exception:
                pass
            return {"status": "forgotten", "id": memory_id}
        return {"status": "not_found", "id": memory_id}

    @server.tool(
        description="Browse stored memories, optionally filtered by category (rule, decision, preference)."
    )
    def list_memories(category: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
        return db_list_memories(conn, category=category, limit=limit)

    return server


def run_mcp_server(
    db_path: Optional[Path] = None,
    md_path: Optional[Path] = None,
    profile: Optional[str] = None,
) -> None:
    """Runs the MCP server over standard input/output for IDE and AI agent communication."""
    server = create_mcp_server(db_path=db_path, md_path=md_path, profile=profile)
    server.run(transport="stdio")
