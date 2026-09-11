from pathlib import Path
from typing import Optional
import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from battery.config import DEFAULT_BATTERY_MD_PATH, DEFAULT_DB_PATH
from battery.db import get_connection, init_db, insert_memory, list_memories, tombstone_memory
from battery.embeddings import embed_text
from battery.mcp_server import run_mcp_server
from battery.retrieval import hybrid_search
from battery.sync import export_battery_md, import_battery_md

app = typer.Typer(
    name="battery",
    help="Battery Context Engine: Sovereign, local-first context substrate for AI workflows."
)
console = Console()

@app.command()
def init(
    db_path: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="Path to SQLite database"),
    md_path: Path = typer.Option(DEFAULT_BATTERY_MD_PATH, "--md", help="Path to living BATTERY.md mirror"),
):
    """Initializes the Battery storage database and living Markdown mirror."""
    conn = get_connection(db_path)
    init_db(conn)
    export_battery_md(conn, md_path)
    console.print(Panel.fit(
        f"[green]✓ Initialized Battery Context Engine[/green]\n"
        f"Database: [bold]{db_path}[/bold]\n"
        f"Mirror:   [bold]{md_path}[/bold]",
        title="Battery Context Engine"
    ))

@app.command()
def add(
    content: str = typer.Argument(..., help="Content of the memory, rule, or decision to save"),
    category: str = typer.Option("general", "-c", "--category", help="Category: rule, decision, preference, general"),
    importance: float = typer.Option(1.0, "-i", "--importance", help="Importance multiplier (0.1 - 2.0)"),
    db_path: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="Path to SQLite database"),
    md_path: Path = typer.Option(DEFAULT_BATTERY_MD_PATH, "--md", help="Path to living BATTERY.md mirror"),
):
    """Saves a new memory, rule, or decision into the local context engine."""
    conn = get_connection(db_path)
    init_db(conn)
    
    with console.status("[cyan]Computing embedding and saving memory...[/cyan]"):
        vec = embed_text(content)
        result = insert_memory(conn, content, vec, category=category, importance=importance)
        export_battery_md(conn, md_path)
        
    status = result["status"]
    mem_id = result["id"]
    if status == "created":
        console.print(f"[green]✓ Saved memory [bold]#{mem_id}[/bold] ({category}):[/green] {content}")
    elif status == "existing":
        console.print(f"[yellow]ℹ Memory already exists as [bold]#{mem_id}[/bold] ({category}):[/yellow] {content}")
    elif status == "restored":
        console.print(f"[cyan]↺ Restored previously deleted memory [bold]#{mem_id}[/bold] ({category}):[/cyan] {content}")

@app.command(name="list")
def list_cmd(
    category: Optional[str] = typer.Option(None, "-c", "--category", help="Filter by category"),
    all_records: bool = typer.Option(False, "--all", help="Include tombstoned records"),
    limit: int = typer.Option(30, "-l", "--limit", help="Max number of items to display"),
    db_path: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="Path to SQLite database"),
):
    """Lists stored memories in a formatted terminal table."""
    conn = get_connection(db_path)
    init_db(conn)
    items = list_memories(conn, category=category, include_deleted=all_records, limit=limit)
    
    if not items:
        console.print("[dim]No memories found in engine.[/dim]")
        return
        
    table = Table(title=f"Battery Memories ({len(items)} items)")
    table.add_column("ID", justify="right", style="cyan", no_wrap=True)
    table.add_column("Category", style="magenta")
    table.add_column("Content", style="white")
    table.add_column("Updated", style="dim")
    
    for item in items:
        deleted_tag = " [red](deleted)[/red]" if item["is_deleted"] else ""
        table.add_row(
            str(item["id"]),
            item["category"],
            item["content"] + deleted_tag,
            item["updated_at"][:19].replace("T", " ")
        )
    console.print(table)

@app.command()
def query(
    query_text: str = typer.Argument(..., help="Search query (natural language or exact keywords)"),
    limit: int = typer.Option(5, "-l", "--limit", help="Max number of results to return"),
    category: Optional[str] = typer.Option(None, "-c", "--category", help="Filter by category"),
    db_path: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="Path to SQLite database"),
):
    """Searches memory using hybrid BM25 + dense vector search fused via RRF."""
    conn = get_connection(db_path)
    init_db(conn)
    
    with console.status("[cyan]Running hybrid search (BM25 + vector + RRF)...[/cyan]"):
        results = hybrid_search(conn, query_text, limit=limit, category=category)
        
    if not results:
        console.print("[dim]No matching memories found.[/dim]")
        return
        
    table = Table(title=f"Hybrid Search Results for: '{query_text}'")
    table.add_column("Score (RRF)", justify="right", style="green", no_wrap=True)
    table.add_column("ID", justify="right", style="cyan", no_wrap=True)
    table.add_column("Category", style="magenta")
    table.add_column("BM25 / Vec Rank", style="yellow")
    table.add_column("Content", style="white")
    
    for r in results:
        ranks = f"#{r.get('bm25_rank') or '-'} / #{r.get('vec_rank') or '-'}"
        table.add_row(
            f"{r['score']:.4f}",
            str(r["id"]),
            r["category"],
            ranks,
            r["content"]
        )
    console.print(table)

@app.command()
def forget(
    memory_id: int = typer.Argument(..., help="ID of memory to tombstone"),
    db_path: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="Path to SQLite database"),
    md_path: Path = typer.Option(DEFAULT_BATTERY_MD_PATH, "--md", help="Path to living BATTERY.md mirror"),
):
    """Tombstones a memory so it no longer matches queries."""
    conn = get_connection(db_path)
    init_db(conn)
    success = tombstone_memory(conn, memory_id)
    if success:
        export_battery_md(conn, md_path)
        console.print(f"[green]✓ Memory [bold]#{memory_id}[/bold] has been tombstoned.[/green]")
    else:
        console.print(f"[red]✗ Memory [bold]#{memory_id}[/bold] not found or already deleted.[/red]")

@app.command()
def sync(
    db_path: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="Path to SQLite database"),
    md_path: Path = typer.Option(DEFAULT_BATTERY_MD_PATH, "--md", help="Path to living BATTERY.md mirror"),
):
    """Synchronizes living BATTERY.md file and SQLite database bidirectionally."""
    conn = get_connection(db_path)
    init_db(conn)
    with console.status("[cyan]Synchronizing BATTERY.md and database...[/cyan]"):
        imported = import_battery_md(conn, md_path)
        export_battery_md(conn, md_path)
    console.print(f"[green]✓ Synchronized {md_path.name} (imported {imported} new entries).[/green]")

@app.command()
def serve():
    """Starts the Model Context Protocol (MCP) server over Stdio."""
    run_mcp_server()

@app.command(name="eval")
def evaluate(
    dataset_path: Optional[Path] = typer.Option(None, "--dataset", "-d", help="Custom evaluation dataset JSON path"),
    markdown: bool = typer.Option(True, "--markdown/--no-markdown", help="Generate evals/benchmark_results.md"),
):
    """Runs the retrieval evaluation benchmark comparing BM25, Vector, and Hybrid RRF."""
    from battery.evals.harness import run_evaluation, load_dataset
    dataset = load_dataset(dataset_path) if dataset_path else None
    run_evaluation(dataset=dataset, output_markdown=markdown)

@app.command()
def setup(
    client: str = typer.Option("all", "--client", "-c", help="Target AI client: 'claude', 'cursor', or 'all'"),
):
    """Configures Battery MCP server automatically in Claude Desktop and/or Cursor configs."""
    import json
    import os
    import platform
    import shutil

    # Determine executable path: prefer 'battery' if on PATH, else absolute uv/python path
    battery_bin = shutil.which("battery") or "battery"

    configs_updated = []
    system = platform.system()

    # 1. Claude Desktop config path
    if client.lower() in ("claude", "all"):
        if system == "Darwin":
            claude_path = Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
        elif system == "Windows":
            appdata = os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming"))
            claude_path = Path(appdata) / "Claude" / "claude_desktop_config.json"
        else:
            claude_path = Path.home() / ".config" / "Claude" / "claude_desktop_config.json"

        try:
            claude_path.parent.mkdir(parents=True, exist_ok=True)
            existing_data: Dict[str, Any] = {}
            if claude_path.exists():
                try:
                    with open(claude_path, "r", encoding="utf-8") as f:
                        existing_data = json.load(f)
                except Exception:
                    existing_data = {}

            if "mcpServers" not in existing_data or not isinstance(existing_data["mcpServers"], dict):
                existing_data["mcpServers"] = {}

            existing_data["mcpServers"]["battery"] = {
                "command": battery_bin,
                "args": ["serve"]
            }

            with open(claude_path, "w", encoding="utf-8") as f:
                json.dump(existing_data, f, indent=2)

            configs_updated.append(("Claude Desktop", claude_path))
        except Exception as e:
            console.print(f"[yellow]⚠ Could not write Claude Desktop config: {e}[/yellow]")

    # 2. Cursor workspace / global config
    if client.lower() in ("cursor", "all"):
        cursor_path = Path.cwd() / ".cursor" / "mcp.json"
        try:
            cursor_path.parent.mkdir(parents=True, exist_ok=True)
            existing_data: Dict[str, Any] = {}
            if cursor_path.exists():
                try:
                    with open(cursor_path, "r", encoding="utf-8") as f:
                        existing_data = json.load(f)
                except Exception:
                    existing_data = {}

            if "mcpServers" not in existing_data or not isinstance(existing_data["mcpServers"], dict):
                existing_data["mcpServers"] = {}

            existing_data["mcpServers"]["battery"] = {
                "command": battery_bin,
                "args": ["serve"]
            }

            with open(cursor_path, "w", encoding="utf-8") as f:
                json.dump(existing_data, f, indent=2)

            configs_updated.append(("Cursor (Workspace)", cursor_path))
        except Exception as e:
            console.print(f"[yellow]⚠ Could not write Cursor config: {e}[/yellow]")

    if configs_updated:
        msg = "[bold green]✓ Battery MCP Server configured successfully![/bold green]\n\n"
        for name, path in configs_updated:
            msg += f"• [cyan]{name}:[/cyan] [dim]{path}[/dim]\n"
        msg += f"\nCommand configured: [bold]{battery_bin} serve[/bold]"
        console.print(Panel.fit(msg, title="1-Click Client Setup"))
    else:
        console.print("[red]✗ No client configs were updated.[/red]")

def main():
    app()

if __name__ == "__main__":
    main()
