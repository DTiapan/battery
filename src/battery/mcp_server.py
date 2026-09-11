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


def format_context_resource(conn: Any, limit_per_category: int = 5) -> str:
    """Formats active rules, decisions, preferences, and recent context into markdown."""
    categories = [
        ("rule", "Active Rules & Constraints"),
        ("decision", "Architectural Decisions"),
        ("preference", "User Preferences & Workflow Habits"),
        ("general", "General Context & Knowledge"),
    ]

    sections: List[str] = []
    has_content = False

    for cat_key, title in categories:
        cursor = conn.execute(
            """
            SELECT id, content, importance
            FROM memories
            WHERE is_deleted = 0 AND category = ?
            ORDER BY importance DESC, id DESC
            LIMIT ?
            """,
            (cat_key, limit_per_category),
        )
        items = cursor.fetchall()
        if items:
            has_content = True
            lines = [f"## {title}"]
            for item in items:
                lines.append(
                    f"- **[ID:{item['id']}]** (importance: {item['importance']:.1f}) {item['content']}"
                )
            sections.append("\n".join(lines))

    if not has_content:
        return (
            "# Battery Sovereign Context\n\n"
            "> **Notice:** Sovereign memory substrate active. No memories recorded yet.\n"
            "> Use the `save_memory` tool or `battery add` CLI command to store context.\n"
        )

    header = (
        "# Battery Sovereign Context\n\n"
        "> **Notice:** Sovereign memory substrate active. Adhere strictly to the active rules "
        "and architectural decisions below before generating code or modifying the project.\n"
    )
    return header + "\n" + "\n\n".join(sections) + "\n"


def format_rules_resource(conn: Any, limit: int = 20) -> str:
    """Formats active rules and constraints into markdown."""
    cursor = conn.execute(
        """
        SELECT id, content, importance
        FROM memories
        WHERE is_deleted = 0 AND category = 'rule'
        ORDER BY importance DESC, id DESC
        LIMIT ?
        """,
        (limit,),
    )
    items = cursor.fetchall()
    if not items:
        return (
            "# Battery Active Rules & Constraints\n\n"
            "> No active rules found. Use `save_memory` with category='rule' to record rules.\n"
        )

    lines = [
        "# Battery Active Rules & Constraints",
        "",
        "> Sovereign rules that must be respected across all conversations and operations.",
        "",
    ]
    for item in items:
        lines.append(
            f"- **[ID:{item['id']}]** (importance: {item['importance']:.1f}) {item['content']}"
        )
    return "\n".join(lines) + "\n"


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
        version="0.2.0",
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
        content: str,
        category: str = "general",
        importance: float = 1.0,
        file_paths: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        vec = embed_text(content)
        citations = [{"file_path": p} for p in (file_paths or []) if p.strip()]
        result = insert_memory(
            conn,
            content,
            vec,
            category=category,
            importance=importance,
            source="mcp",
            citations=citations or None,
        )
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

    @server.resource(
        "battery://context",
        name="battery_context",
        title="Battery Sovereign Context",
        description="Curated active sovereign context, project constraints, and architectural decisions.",
        mime_type="text/markdown",
    )
    def get_context_resource() -> str:
        return format_context_resource(conn)

    @server.resource(
        "battery://rules",
        name="battery_rules",
        title="Battery Active Rules & Constraints",
        description="Active sovereign rules and constraints stored in Battery.",
        mime_type="text/markdown",
    )
    def get_rules_resource() -> str:
        return format_rules_resource(conn)

    @server.prompt(
        name="battery-context",
        description=(
            "Proactively inject Battery sovereign context, active rules, "
            "and task-relevant memories into the conversation."
        ),
    )
    def battery_context_prompt(task: str = "") -> str:
        cursor = conn.execute(
            """
            SELECT id, content, importance
            FROM memories
            WHERE is_deleted = 0 AND category = 'rule'
            ORDER BY importance DESC, id DESC
            LIMIT 5
            """
        )
        rules = cursor.fetchall()

        lines = [
            "You are an AI assistant equipped with the Battery Sovereign Context Engine.",
            "",
            "## Sovereign Memory Directives",
            "- Always follow the active project rules and architectural constraints documented below.",
            "- Use the `recall_memory` tool to proactively query past decisions or patterns when unsure.",
            "- Persist new user decisions, architectural choices, and constraints using `save_memory`.",
            "",
        ]

        if rules:
            lines.append("## Active Rules & Constraints")
            for r in rules:
                lines.append(
                    f"- **[ID:{r['id']}]** (importance: {r['importance']:.1f}) {r['content']}"
                )
            lines.append("")

        task_clean = task.strip()
        if task_clean:
            try:
                relevant = hybrid_search(conn, task_clean, limit=5)
            except Exception:
                relevant = []

            if relevant:
                lines.append(f'## Task-Relevant Memories for "{task_clean}"')
                for m in relevant:
                    cat = m.get("category", "general")
                    score = m.get("rrf_score", 0.0)
                    lines.append(
                        f"- **[ID:{m['id']}]** [{cat.upper()}] (score: {score:.4f}) {m['content']}"
                    )
                lines.append("")
            else:
                lines.append(f"## Current Task\nFocusing on: {task_clean}\n")
        else:
            cursor = conn.execute(
                """
                SELECT id, content, category, importance
                FROM memories
                WHERE is_deleted = 0 AND category IN ('decision', 'preference')
                ORDER BY importance DESC, id DESC
                LIMIT 6
                """
            )
            other_items = cursor.fetchall()
            if other_items:
                lines.append("## Key Architectural Decisions & Preferences")
                for item in other_items:
                    lines.append(
                        f"- **[ID:{item['id']}]** [{item['category'].upper()}] {item['content']}"
                    )
                lines.append("")

        return "\n".join(lines).strip()

    return server


def run_mcp_server(
    db_path: Optional[Path] = None,
    md_path: Optional[Path] = None,
    profile: Optional[str] = None,
) -> None:
    """Runs the MCP server over standard input/output for IDE and AI agent communication."""
    server = create_mcp_server(db_path=db_path, md_path=md_path, profile=profile)
    server.run(transport="stdio")
