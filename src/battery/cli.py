import json
import os
import platform
import shutil
from pathlib import Path
from typing import Any, Dict, Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from battery.config import (
    delete_profile,
    get_active_profile,
    get_profile_db_path,
    get_profile_md_path,
    list_profiles,
    set_active_profile,
)
from battery.db import get_connection, init_db, insert_memory, list_memories, tombstone_memory
from battery.embeddings import embed_text
from battery.mcp_server import run_mcp_server
from battery.retrieval import hybrid_search
from battery.sync import export_battery_md, import_battery_md

app = typer.Typer(
    name="battery",
    help="Battery Context Engine: Sovereign, local-first context substrate for AI workflows.",
)
profile_app = typer.Typer(name="profile", help="Manage isolated multi-battery context profiles.")
app.add_typer(profile_app, name="profile")
console = Console()


def resolve_paths(
    profile: Optional[str] = None,
    db_path: Optional[Path] = None,
    md_path: Optional[Path] = None,
) -> tuple[Path, Path]:
    resolved_db = db_path if db_path is not None else get_profile_db_path(profile)
    resolved_md = md_path if md_path is not None else get_profile_md_path(profile)
    return resolved_db, resolved_md


@app.command()
def init(
    profile: Optional[str] = typer.Option(None, "--profile", "-p", help="Target context profile"),
    db_path: Optional[Path] = typer.Option(None, "--db", help="Path to SQLite database"),
    md_path: Optional[Path] = typer.Option(None, "--md", help="Path to living BATTERY.md mirror"),
):
    """Initializes the Battery storage database and living Markdown mirror."""
    resolved_db, resolved_md = resolve_paths(profile, db_path, md_path)
    conn = get_connection(resolved_db)
    init_db(conn)
    export_battery_md(conn, resolved_md)
    console.print(
        Panel.fit(
            f"[green]✓ Initialized Battery Context Engine[/green]\n"
            f"Profile:  [bold cyan]{profile or get_active_profile()}[/bold cyan]\n"
            f"Database: [bold]{resolved_db}[/bold]\n"
            f"Mirror:   [bold]{resolved_md}[/bold]",
            title="Battery Context Engine",
        )
    )


@app.command()
def add(
    content: str = typer.Argument(..., help="Content of the memory, rule, or decision to save"),
    category: str = typer.Option(
        "general", "-c", "--category", help="Category: rule, decision, preference, general"
    ),
    importance: float = typer.Option(
        1.0, "-i", "--importance", help="Importance multiplier (0.1 - 2.0)"
    ),
    profile: Optional[str] = typer.Option(None, "--profile", "-p", help="Target context profile"),
    db_path: Optional[Path] = typer.Option(None, "--db", help="Path to SQLite database"),
    md_path: Optional[Path] = typer.Option(None, "--md", help="Path to living BATTERY.md mirror"),
):
    """Saves a new memory, rule, or decision into the local context engine."""
    resolved_db, resolved_md = resolve_paths(profile, db_path, md_path)
    conn = get_connection(resolved_db)
    init_db(conn)

    with console.status("[cyan]Computing embedding and saving memory...[/cyan]"):
        vec = embed_text(content)
        result = insert_memory(conn, content, vec, category=category, importance=importance)
        export_battery_md(conn, resolved_md)

    status = result["status"]
    mem_id = result["id"]
    if status == "created":
        console.print(
            f"[green]✓ Saved memory [bold]#{mem_id}[/bold] ({category}):[/green] {content}"
        )
    elif status == "existing":
        console.print(
            f"[yellow]ℹ Memory already exists as [bold]#{mem_id}[/bold] ({category}):[/yellow] {content}"
        )
    elif status == "restored":
        console.print(
            f"[cyan]↺ Restored previously deleted memory [bold]#{mem_id}[/bold] ({category}):[/cyan] {content}"
        )


@app.command(name="list")
def list_cmd(
    category: Optional[str] = typer.Option(None, "-c", "--category", help="Filter by category"),
    all_records: bool = typer.Option(False, "--all", help="Include tombstoned records"),
    limit: int = typer.Option(30, "-l", "--limit", help="Max number of items to display"),
    profile: Optional[str] = typer.Option(None, "--profile", "-p", help="Target context profile"),
    db_path: Optional[Path] = typer.Option(None, "--db", help="Path to SQLite database"),
):
    """Lists stored memories in a formatted terminal table."""
    resolved_db, _ = resolve_paths(profile, db_path, None)
    conn = get_connection(resolved_db)
    init_db(conn)
    items = list_memories(conn, category=category, include_deleted=all_records, limit=limit)

    if not items:
        console.print(
            f"[dim]No memories found in profile '{profile or get_active_profile()}'.[/dim]"
        )
        return

    table = Table(
        title=f"Battery Memories — [{profile or get_active_profile()}] ({len(items)} items)"
    )
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
            item["updated_at"][:19].replace("T", " "),
        )
    console.print(table)


@app.command()
def query(
    query_text: str = typer.Argument(..., help="Search query (natural language or exact keywords)"),
    limit: int = typer.Option(5, "-l", "--limit", help="Max number of results to return"),
    category: Optional[str] = typer.Option(None, "-c", "--category", help="Filter by category"),
    profile: Optional[str] = typer.Option(None, "--profile", "-p", help="Target context profile"),
    db_path: Optional[Path] = typer.Option(None, "--db", help="Path to SQLite database"),
):
    """Searches memory using hybrid BM25 + dense vector search fused via RRF."""
    resolved_db, _ = resolve_paths(profile, db_path, None)
    conn = get_connection(resolved_db)
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
        table.add_row(f"{r['score']:.4f}", str(r["id"]), r["category"], ranks, r["content"])
    console.print(table)


@app.command()
def forget(
    memory_id: int = typer.Argument(..., help="ID of memory to tombstone"),
    profile: Optional[str] = typer.Option(None, "--profile", "-p", help="Target context profile"),
    db_path: Optional[Path] = typer.Option(None, "--db", help="Path to SQLite database"),
    md_path: Optional[Path] = typer.Option(None, "--md", help="Path to living BATTERY.md mirror"),
):
    """Tombstones a memory so it no longer matches queries."""
    resolved_db, resolved_md = resolve_paths(profile, db_path, md_path)
    conn = get_connection(resolved_db)
    init_db(conn)
    success = tombstone_memory(conn, memory_id)
    if success:
        export_battery_md(conn, resolved_md)
        console.print(f"[green]✓ Memory [bold]#{memory_id}[/bold] has been tombstoned.[/green]")
    else:
        console.print(
            f"[red]✗ Memory [bold]#{memory_id}[/bold] not found or already deleted.[/red]"
        )


@app.command()
def sync(
    profile: Optional[str] = typer.Option(None, "--profile", "-p", help="Target context profile"),
    db_path: Optional[Path] = typer.Option(None, "--db", help="Path to SQLite database"),
    md_path: Optional[Path] = typer.Option(None, "--md", help="Path to living BATTERY.md mirror"),
):
    """Synchronizes living BATTERY.md file and SQLite database bidirectionally."""
    resolved_db, resolved_md = resolve_paths(profile, db_path, md_path)
    conn = get_connection(resolved_db)
    init_db(conn)
    with console.status("[cyan]Synchronizing BATTERY.md and database...[/cyan]"):
        imported = import_battery_md(conn, resolved_md)
        export_battery_md(conn, resolved_md)
    console.print(
        f"[green]✓ Synchronized {resolved_md.name} (imported {imported} new entries).[/green]"
    )


@app.command()
def serve(
    profile: Optional[str] = typer.Option(None, "--profile", "-p", help="Target context profile"),
    db_path: Optional[Path] = typer.Option(None, "--db", help="Explicit path to SQLite database"),
    md_path: Optional[Path] = typer.Option(
        None, "--md", help="Explicit path to living BATTERY.md mirror"
    ),
):
    """Starts the Model Context Protocol (MCP) server over Stdio."""
    resolved_db, resolved_md = resolve_paths(profile, db_path, md_path)
    run_mcp_server(db_path=resolved_db, md_path=resolved_md, profile=profile)


@app.command(name="use")
def use_profile(
    name: str = typer.Argument(..., help="Name of context profile to activate"),
):
    """Sets the active context profile (Phase 2 roadmap alias for 'battery profile switch')."""
    try:
        set_active_profile(name)
        console.print(f"[green]✓ Switched active profile to [bold]'{name}'[/bold][/green]")
    except Exception as e:
        console.print(f"[red]✗ Error switching profile: {e}[/red]")
        raise typer.Exit(code=1)


@profile_app.command(name="list")
def profile_list():
    """Lists all configured context profiles."""
    profiles = list_profiles()
    table = Table(title="Battery Context Profiles")
    table.add_column("Profile", style="bold cyan")
    table.add_column("Active", justify="center")
    table.add_column("Database Path", style="dim")
    table.add_column("Status", justify="center")

    for p in profiles:
        active_mark = "[bold green]● Active[/bold green]" if p["is_active"] else "[dim]○[/dim]"
        status = "[green]Initialized[/green]" if p["exists"] else "[yellow]Uninitialized[/yellow]"
        table.add_row(p["name"], active_mark, str(p["db_path"]), status)
    console.print(table)


@profile_app.command(name="create")
def profile_create(
    name: str = typer.Argument(..., help="Name of new context profile to create"),
):
    """Creates and initializes a new isolated context profile."""
    try:
        db_path = get_profile_db_path(name)
        md_path = get_profile_md_path(name)
        conn = get_connection(db_path)
        init_db(conn)
        export_battery_md(conn, md_path)
        console.print(f"[green]✓ Created and initialized profile [bold]'{name}'[/bold][/green]")
        console.print(f"  Database: [dim]{db_path}[/dim]")
        console.print(f"  Mirror:   [dim]{md_path}[/dim]")
    except Exception as e:
        console.print(f"[red]✗ Error creating profile: {e}[/red]")
        raise typer.Exit(code=1)


@profile_app.command(name="switch")
def profile_switch(
    name: str = typer.Argument(..., help="Name of context profile to activate"),
):
    """Sets the active context profile."""
    try:
        set_active_profile(name)
        console.print(f"[green]✓ Switched active profile to [bold]'{name}'[/bold][/green]")
    except Exception as e:
        console.print(f"[red]✗ Error switching profile: {e}[/red]")
        raise typer.Exit(code=1)


@profile_app.command(name="current")
def profile_current():
    """Displays the currently active context profile."""
    active = get_active_profile()
    db_path = get_profile_db_path(active)
    console.print(f"Active Profile: [bold cyan]{active}[/bold cyan] ([dim]{db_path}[/dim])")


@profile_app.command(name="delete")
def profile_delete(
    name: str = typer.Argument(..., help="Name of context profile to delete"),
    force: bool = typer.Option(False, "--force", "-f", help="Force deletion without confirmation"),
):
    """Deletes an isolated context profile."""
    if not force:
        confirm = typer.confirm(
            f"Are you sure you want to delete profile '{name}' and all its memories?"
        )
        if not confirm:
            console.print("[dim]Cancelled.[/dim]")
            return
    try:
        deleted = delete_profile(name)
        if deleted:
            console.print(f"[green]✓ Deleted profile [bold]'{name}'[/bold][/green]")
        else:
            console.print(f"[yellow]Profile '{name}' did not exist or had no data.[/yellow]")
    except Exception as e:
        console.print(f"[red]✗ Error deleting profile: {e}[/red]")
        raise typer.Exit(code=1)


@app.command(name="eval")
def evaluate(
    dataset_path: Optional[Path] = typer.Option(
        None, "--dataset", "-d", help="Custom evaluation dataset JSON path"
    ),
    markdown: bool = typer.Option(
        True, "--markdown/--no-markdown", help="Generate evals/benchmark_results.md"
    ),
):
    """Runs the retrieval evaluation benchmark comparing BM25, Vector, and Hybrid RRF."""
    from battery.evals.harness import load_dataset, run_evaluation

    dataset = load_dataset(dataset_path) if dataset_path else None
    run_evaluation(dataset=dataset, output_markdown=markdown)


@app.command()
def setup(
    client: str = typer.Option(
        "all", "--client", "-c", help="Target AI client: 'claude', 'cursor', or 'all'"
    ),
    profile: Optional[str] = typer.Option(
        None, "--profile", "-p", help="Profile to configure in client"
    ),
):
    """Configures Battery MCP server automatically in Claude Desktop and/or Cursor configs."""
    battery_bin = shutil.which("battery") or "battery"
    args = ["serve"]
    if profile:
        args.extend(["--profile", profile])

    configs_updated = []
    system = platform.system()

    # 1. Claude Desktop config path
    if client.lower() in ("claude", "all"):
        if system == "Darwin":
            claude_path = (
                Path.home()
                / "Library"
                / "Application Support"
                / "Claude"
                / "claude_desktop_config.json"
            )
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

            if "mcpServers" not in existing_data or not isinstance(
                existing_data["mcpServers"], dict
            ):
                existing_data["mcpServers"] = {}

            server_key = f"battery_{profile}" if profile else "battery"
            existing_data["mcpServers"][server_key] = {"command": battery_bin, "args": args}

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

            if "mcpServers" not in existing_data or not isinstance(
                existing_data["mcpServers"], dict
            ):
                existing_data["mcpServers"] = {}

            server_key = f"battery_{profile}" if profile else "battery"
            existing_data["mcpServers"][server_key] = {"command": battery_bin, "args": args}

            with open(cursor_path, "w", encoding="utf-8") as f:
                json.dump(existing_data, f, indent=2)

            configs_updated.append(("Cursor (Workspace)", cursor_path))
        except Exception as e:
            console.print(f"[yellow]⚠ Could not write Cursor config: {e}[/yellow]")

    if configs_updated:
        msg = "[bold green]✓ Battery MCP Server configured successfully![/bold green]\n\n"
        for name, path in configs_updated:
            msg += f"• [cyan]{name}:[/cyan] [dim]{path}[/dim]\n"
        cmd_str = f"{battery_bin} {' '.join(args)}"
        msg += f"\nCommand configured: [bold]{cmd_str}[/bold]"
        console.print(Panel.fit(msg, title="1-Click Client Setup"))
    else:
        console.print("[red]✗ No client configs were updated.[/red]")


def main():
    app()


if __name__ == "__main__":
    main()
