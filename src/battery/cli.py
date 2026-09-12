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
from battery.prune import prune_stale_memories
from battery.retrieval import hybrid_search
from battery.sync import export_battery_md, import_battery_md

app = typer.Typer(
    name="battery",
    help="Battery Context Engine: Sovereign, local-first context substrate for AI workflows.",
)
profile_app = typer.Typer(name="profile", help="Manage isolated multi-battery context profiles.")
hook_app = typer.Typer(name="hook", help="Install and run Claude Code lifecycle hooks.")
checkpoint_app = typer.Typer(name="checkpoint", help="Inspect session checkpoints.")
handoff_app = typer.Typer(name="handoff", help="Export and load cross-tool session handoffs.")
git_app = typer.Typer(name="git", help="Git post-commit episodic capture.")
app.add_typer(profile_app, name="profile")
app.add_typer(hook_app, name="hook")
app.add_typer(checkpoint_app, name="checkpoint")
app.add_typer(handoff_app, name="handoff")
app.add_typer(git_app, name="git")
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
    elif status == "merged":
        similarity = result.get("similarity", 0.0)
        console.print(
            f"[cyan]↺ Merged near-duplicate into [bold]#{mem_id}[/bold] "
            f"(similarTo={mem_id}, similarity={similarity:.3f}):[/cyan] {content}"
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
    stress: bool = typer.Option(
        False, "--stress", "-s", help="Run scaled stress benchmark (500 items under load)"
    ),
    scale: int = typer.Option(500, "--scale", help="Scale factor for stress benchmark"),
    real: bool = typer.Option(
        False, "--real", "-r", help="Run real-world evaluation on Battery's own ADR/README corpus"
    ),
    rot: bool = typer.Option(
        False, "--rot", help="Run context rot benchmark (JIT verify + prune scenarios)"
    ),
    handoff_eval: bool = typer.Option(
        False,
        "--handoff",
        help="Run cross-tool handoff scenario benchmark (Cursor ↔ Claude continuity)",
    ),
    dedup_stress: bool = typer.Option(
        False,
        "--dedup-stress",
        help="Run near-duplicate re-ingest stress benchmark (row bloat + MRR gate)",
    ),
    tune: bool = typer.Option(
        False, "--tune", "-t", help="Run RRF k/weight grid sweep to find optimal parameters"
    ),
    comparative: bool = typer.Option(
        False,
        "--comparative",
        help="Run Tier 1 comparative eval (Sediment benchmark harness)",
    ),
    tier: str = typer.Option(
        "sediment",
        "--tier",
        help="Comparative tier: sediment (Tier 1 public benchmark)",
    ),
    systems: str = typer.Option(
        "battery",
        "--systems",
        help="Comma-separated systems for --comparative (battery, battery-bm25, chromadb, ...)",
    ),
    phases: str = typer.Option(
        "retrieval",
        "--phases",
        help="Sediment phases for --comparative: retrieval, latency, or all",
    ),
    write_report: bool = typer.Option(
        False,
        "--write-report",
        help="After --comparative run, generate comparative_benchmark_report.md",
    ),
    markdown: bool = typer.Option(
        True, "--markdown/--no-markdown", help="Generate Markdown evaluation report"
    ),
):
    """Runs retrieval evaluation benchmarks comparing BM25, Vector, and Hybrid RRF.

    Modes:
      (default)   Golden 15-query benchmark on curated seed dataset
      --real      Real-world benchmark on Battery's own ADR/README corpus (~100 items, 30 queries)
      --rot       Context rot benchmark: stale citation filtering + prune scenarios
      --handoff   Cross-tool handoff benchmark: export/load + lineage scenarios
      --dedup-stress  Near-dup re-ingest stress: duplicate reduction + MRR gate
      --stress    500-item scaled stress test measuring throughput and latency under load
      --tune      RRF k/weight grid sweep: empirically find optimal hybrid search parameters
      --comparative  Tier 1 Sediment benchmark (battery vs competitors on public 1k/200 dataset)
    """
    if comparative:
        if tier != "sediment":
            console.print(f"[red]Unknown comparative tier: {tier}. Only 'sediment' is implemented.[/red]")
            raise typer.Exit(code=1)
        from battery.evals.sediment.runner import run_sediment_benchmark

        console.print(
            "[cyan]Running Tier 1 comparative eval (Sediment benchmark)...[/cyan]\n"
            f"[dim]Systems: {systems} | Phases: {phases}[/dim]"
        )
        run_sediment_benchmark(systems=systems, phases=phases, write_report=write_report)
        return

    if stress:
        from battery.evals.stress_test import run_stress_benchmark

        run_stress_benchmark(scale=scale, output_markdown=markdown)
        return

    if real:
        from battery.evals.realworld_harness import run_realworld_evaluation

        run_realworld_evaluation(output_markdown=markdown)
        return

    if rot:
        from battery.evals.rot_harness import run_rot_benchmark

        run_rot_benchmark(output_markdown=markdown)
        return

    if handoff_eval:
        from battery.evals.handoff_harness import run_handoff_benchmark

        run_handoff_benchmark(output_markdown=markdown)
        return

    if dedup_stress:
        from battery.evals.dedup_stress_harness import run_dedup_stress_benchmark

        run_dedup_stress_benchmark(scale=scale if stress else 500, output_markdown=markdown)
        return

    if tune:
        from battery.evals.rrf_tuner import run_rrf_tuner

        run_rrf_tuner(output_markdown=markdown)
        return

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

    console.print(
        "\n[dim]Tip: Enable MCP resources in your client UI so battery://context loads at session start.[/dim]"
    )
    console.print(
        "[dim]For Claude Code auto-capture, run: [bold]battery hook install --scope project[/bold][/dim]"
    )


@app.command()
def onboard(
    client: str = typer.Option(
        "all", "--client", "-c", help="Target AI client: 'claude', 'cursor', or 'all'"
    ),
    profile: Optional[str] = typer.Option(None, "--profile", "-p", help="Target context profile"),
    db_path: Optional[Path] = typer.Option(None, "--db", help="Path to SQLite database"),
    md_path: Optional[Path] = typer.Option(None, "--md", help="Path to living BATTERY.md mirror"),
    seed: bool = typer.Option(True, "--seed/--no-seed", help="Seed starter memories when empty"),
    skip_setup: bool = typer.Option(
        False, "--skip-setup", help="Skip MCP client registration (init + doctor only)"
    ),
):
    """One-shot init, optional seed memories, MCP setup, and adoption doctor."""
    from battery.doctor import ONBOARD_SEED_MEMORIES, run_doctor

    resolved_db, resolved_md = resolve_paths(profile, db_path, md_path)
    conn = get_connection(resolved_db)
    init_db(conn)
    export_battery_md(conn, resolved_md)

    row = conn.execute("SELECT COUNT(*) FROM memories WHERE is_deleted = 0").fetchone()
    memory_count = row[0] if row else 0
    seeded = 0
    if seed and memory_count == 0:
        with console.status("[cyan]Seeding starter memories...[/cyan]"):
            for content, category in ONBOARD_SEED_MEMORIES:
                vec = embed_text(content)
                insert_memory(conn, content, vec, category=category, importance=1.0)
                seeded += 1
            export_battery_md(conn, resolved_md)

    if not skip_setup:
        setup(client=client, profile=profile)

    report = run_doctor(conn, resolved_md, adoption=True, project_dir=Path.cwd())

    table = Table(title="Battery Onboard")
    table.add_column("Check", style="bold")
    table.add_column("Status", justify="center")
    table.add_column("Detail")

    for check in report["checks"]:
        status = "[green]PASS[/green]" if check["ok"] else "[red]FAIL[/red]"
        table.add_row(check["name"], status, check["detail"])
        if not check["ok"] and check.get("fix"):
            table.add_row("", "", f"[yellow]Fix:[/yellow] {check['fix']}")

    console.print(table)
    console.print(
        Panel.fit(
            f"[green]✓ Onboard complete[/green]\n"
            f"Database: [bold]{resolved_db}[/bold]\n"
            f"Mirror:   [bold]{resolved_md}[/bold]\n"
            f"Seeded:   [bold]{seeded}[/bold] starter memories",
            title="Battery Context Engine",
        )
    )

    if report["healthy"]:
        console.print(
            "[green]✓ Adoption checks passed — recall and MCP resources are ready[/green]"
        )
    else:
        console.print(
            f"[yellow]⚠ {report['passed']}/{report['total']} adoption checks passed[/yellow]"
        )
        raise typer.Exit(code=1)


@app.command()
def prune(
    dry_run: bool = typer.Option(False, "--dry-run", help="Report stale memories without deleting"),
    since_commit: Optional[str] = typer.Option(
        None, "--since-commit", help="Only consider git deletions since this commit"
    ),
    profile: Optional[str] = typer.Option(None, "--profile", "-p", help="Target context profile"),
    db_path: Optional[Path] = typer.Option(None, "--db", help="Path to SQLite database"),
):
    """Tombstones memories with stale or missing file citations."""
    resolved_db, _ = resolve_paths(profile, db_path, None)
    conn = get_connection(resolved_db)
    init_db(conn)
    result = prune_stale_memories(
        conn,
        project_root=Path.cwd(),
        since_commit=since_commit,
        dry_run=dry_run,
    )
    label = "Would prune" if dry_run else "Pruned"
    console.print(
        f"[green]✓ {label} {len(result['pruned_ids'])} / {result['candidates']} stale memories[/green]"
    )
    for mem in result["memories"][:10]:
        console.print(f"  [dim]#{mem['id']}[/dim] ({mem.get('reason')}) {mem['content'][:80]}...")


@app.command()
def doctor(
    adoption: bool = typer.Option(False, "--adoption", help="Include MCP and hook adoption checks"),
    profile: Optional[str] = typer.Option(None, "--profile", "-p", help="Target context profile"),
    db_path: Optional[Path] = typer.Option(None, "--db", help="Path to SQLite database"),
    md_path: Optional[Path] = typer.Option(None, "--md", help="Path to living BATTERY.md mirror"),
):
    """Runs Battery health and adoption diagnostics."""
    from battery.doctor import run_doctor

    resolved_db, resolved_md = resolve_paths(profile, db_path, md_path)
    conn = get_connection(resolved_db)
    init_db(conn)
    report = run_doctor(conn, resolved_md, adoption=adoption, project_dir=Path.cwd())

    table = Table(title="Battery Doctor")
    table.add_column("Check", style="bold")
    table.add_column("Status", justify="center")
    table.add_column("Detail")

    for check in report["checks"]:
        status = "[green]PASS[/green]" if check["ok"] else "[red]FAIL[/red]"
        table.add_row(check["name"], status, check["detail"])
        if not check["ok"] and check.get("fix"):
            table.add_row("", "", f"[yellow]Fix:[/yellow] {check['fix']}")

    console.print(table)
    if report["healthy"]:
        console.print("[green]✓ Battery is healthy[/green]")
    else:
        console.print(f"[yellow]⚠ {report['passed']}/{report['total']} checks passed[/yellow]")
        raise typer.Exit(code=1)


@profile_app.command(name="export")
def profile_export(
    profile: Optional[str] = typer.Option(None, "--profile", "-p", help="Profile to export"),
    out: Path = typer.Option(
        Path("battery-export.battery-bundle"),
        "--out",
        "-o",
        help="Output .battery-bundle path",
    ),
    include_md: bool = typer.Option(
        False, "--include-md", help="Include BATTERY.md mirror snapshot in bundle"
    ),
    md_path: Optional[Path] = typer.Option(None, "--md", help="Path to BATTERY.md mirror"),
):
    """Exports a profile to a portable .battery-bundle archive."""
    import importlib.metadata

    from battery.portability import export_profile_bundle

    prof = profile or get_active_profile()
    try:
        version = importlib.metadata.version("battery")
    except importlib.metadata.PackageNotFoundError:
        version = "0.0.0"

    try:
        result = export_profile_bundle(
            profile=prof,
            out_path=out,
            md_path=md_path,
            include_md=include_md,
            battery_version=version,
        )
    except FileNotFoundError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    console.print(
        Panel.fit(
            f"[green]✓ Exported profile [bold]{prof}[/bold][/green]\n"
            f"Bundle: [dim]{result['path']}[/dim]\n"
            f"Files: {', '.join(result['files'])}\n"
            f"[dim]ONNX weights not included — re-download on first embed[/dim]",
            title="Profile Export",
        )
    )


@profile_app.command(name="import")
def profile_import_cmd(
    bundle: Path = typer.Argument(..., help="Path to .battery-bundle file"),
    profile: Optional[str] = typer.Option(
        None, "--profile", "-p", help="Target profile name (defaults to bundle manifest)"
    ),
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite existing profile database"),
    md_path: Optional[Path] = typer.Option(None, "--md", help="Restore BATTERY.md to this path"),
):
    """Imports a portable .battery-bundle archive into a local profile."""
    from battery.portability import import_profile_bundle

    try:
        result = import_profile_bundle(
            bundle,
            profile=profile,
            md_path=md_path,
            force=force,
        )
    except (FileNotFoundError, FileExistsError, ValueError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    lines = [
        f"[green]✓ Imported profile [bold]{result['profile']}[/bold][/green]",
        f"Database: [dim]{result['db_path']}[/dim]",
        f"Schema: v{result['schema_version']}",
    ]
    if result.get("md_path"):
        lines.append(f"Mirror: [dim]{result['md_path']}[/dim]")
    console.print(Panel.fit("\n".join(lines), title="Profile Import"))


@profile_app.command(name="inspect")
def profile_inspect(
    bundle: Path = typer.Argument(..., help="Path to .battery-bundle file"),
):
    """Shows manifest metadata for a bundle without importing."""
    from battery.portability import inspect_bundle

    try:
        manifest = inspect_bundle(bundle)
    except (FileNotFoundError, ValueError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    table = Table(title="Battery Bundle")
    table.add_column("Field", style="bold")
    table.add_column("Value")
    for key in (
        "bundle_format",
        "bundle_version",
        "profile",
        "schema_version",
        "embedding_model",
        "exported_at",
        "battery_version",
        "includes_mirror",
    ):
        if key in manifest:
            table.add_row(key, str(manifest[key]))
    console.print(table)


@git_app.command(name="install")
def git_install():
    """Installs Battery post-commit hook in the current git repository."""
    from battery.git_hooks import install_git_hook

    try:
        result = install_git_hook(Path.cwd())
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    status = "already present" if result.get("already_installed") else "installed"
    console.print(
        Panel.fit(
            f"[green]✓ Git post-commit hook {status}[/green]\n"
            f"Hook: [dim]{result['hook_path']}[/dim]",
            title="Git Hook Install",
        )
    )


@git_app.command(name="uninstall")
def git_uninstall():
    """Removes Battery post-commit hook from the current git repository."""
    from battery.git_hooks import uninstall_git_hook

    result = uninstall_git_hook(Path.cwd())
    console.print(f"[green]✓ Removed Battery git hook[/green] ([dim]{result['hook_path']}[/dim])")


@git_app.command(name="capture")
def git_capture_cmd(
    commit: Optional[str] = typer.Option(None, "--commit", help="Capture a specific commit SHA"),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress output (for git hooks)"),
    profile: Optional[str] = typer.Option(None, "--profile", "-p", help="Target context profile"),
    db_path: Optional[Path] = typer.Option(None, "--db", help="Path to SQLite database"),
):
    """Captures the latest git commit as episodic memory."""
    from battery.git_capture import capture_commit

    resolved_db, _ = resolve_paths(profile, db_path, None)
    conn = get_connection(resolved_db)
    init_db(conn)

    try:
        result = capture_commit(conn, Path.cwd(), commit_sha=commit)
        conn.commit()
    except (ValueError, RuntimeError) as exc:
        if not quiet:
            console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    if quiet:
        return

    if result["status"] == "existing":
        console.print(
            f"[yellow]ℹ Commit [bold]{result['short_sha']}[/bold] already captured[/yellow]"
        )
        return

    console.print(
        f"[green]✓ Captured commit [bold]{result['short_sha']}[/bold] "
        f"as episodic memory #{result['memory_id']}[/green] "
        f"({result['files']} files)"
    )


@hook_app.command(name="install")
def hook_install(
    scope: str = typer.Option(
        "project", "--scope", "-s", help="Install scope: 'project' or 'user'"
    ),
):
    """Installs Battery lifecycle hooks into Claude Code settings."""
    from battery.hooks import install_hooks

    if scope not in ("project", "user"):
        console.print("[red]Scope must be 'project' or 'user'[/red]")
        raise typer.Exit(code=1)
    result = install_hooks(scope=scope)  # type: ignore[arg-type]
    console.print(
        Panel.fit(
            f"[green]✓ Installed Battery hooks ({scope})[/green]\n"
            f"Settings: [dim]{result['settings_path']}[/dim]\n"
            f"Events: {', '.join(result['events'])}",
            title="Hook Install",
        )
    )


@hook_app.command(name="uninstall")
def hook_uninstall(
    scope: str = typer.Option(
        "project", "--scope", "-s", help="Install scope: 'project' or 'user'"
    ),
):
    """Removes Battery lifecycle hooks from Claude Code settings."""
    from battery.hooks import uninstall_hooks

    if scope not in ("project", "user"):
        console.print("[red]Scope must be 'project' or 'user'[/red]")
        raise typer.Exit(code=1)
    result = uninstall_hooks(scope=scope)  # type: ignore[arg-type]
    console.print(f"[green]✓ Removed hooks from {result['settings_path']}[/green]")


@hook_app.command(name="run")
def hook_run(
    profile: Optional[str] = typer.Option(None, "--profile", "-p", help="Target context profile"),
    db_path: Optional[Path] = typer.Option(None, "--db", help="Path to SQLite database"),
    md_path: Optional[Path] = typer.Option(None, "--md", help="Path to living BATTERY.md mirror"),
):
    """Entrypoint for Claude Code hooks (reads JSON from stdin)."""
    import sys

    from battery.checkpoint import handle_hook_event, parse_hook_stdin

    raw = sys.stdin.read()
    hook_input = parse_hook_stdin(raw)
    resolved_db, resolved_md = resolve_paths(profile, db_path, md_path)
    conn = get_connection(resolved_db)
    init_db(conn)

    try:
        result = handle_hook_event(conn, hook_input, resolved_md)
        conn.commit()
    except Exception as exc:
        console.print(json.dumps({"status": "error", "message": str(exc)}))
        raise typer.Exit(code=1) from exc

    if result.get("additionalContext"):
        print(
            json.dumps({"hookSpecificOutput": {"additionalContext": result["additionalContext"]}})
        )
    else:
        print(json.dumps(result))


@checkpoint_app.command(name="list")
def checkpoint_list(
    limit: int = typer.Option(10, "--limit", "-n", help="Max checkpoints to show"),
    profile: Optional[str] = typer.Option(None, "--profile", "-p", help="Target context profile"),
    db_path: Optional[Path] = typer.Option(None, "--db", help="Path to SQLite database"),
):
    """Lists recent session checkpoints for the current project."""
    from battery.db import list_session_checkpoints

    resolved_db, _ = resolve_paths(profile, db_path, None)
    conn = get_connection(resolved_db)
    init_db(conn)
    rows = list_session_checkpoints(conn, project_root=str(Path.cwd()), limit=limit)
    if not rows:
        console.print("[dim]No checkpoints found for this project.[/dim]")
        return
    table = Table(title="Session Checkpoints")
    table.add_column("ID")
    table.add_column("Session")
    table.add_column("Event")
    table.add_column("Memory")
    table.add_column("Created")
    for row in rows:
        table.add_row(
            str(row["id"]),
            row["session_id"][:12],
            row["event_type"],
            str(row.get("memory_id") or "-"),
            row["created_at"][:19],
        )
    console.print(table)


@checkpoint_app.command(name="show")
def checkpoint_show(
    checkpoint_id: Optional[int] = typer.Option(None, "--id", help="Checkpoint ID"),
    latest: bool = typer.Option(True, "--latest", help="Show latest checkpoint when --id omitted"),
    profile: Optional[str] = typer.Option(None, "--profile", "-p", help="Target context profile"),
    db_path: Optional[Path] = typer.Option(None, "--db", help="Path to SQLite database"),
):
    """Shows checkpoint payload as markdown."""
    from battery.checkpoint import _checkpoint_content
    from battery.db import list_session_checkpoints

    resolved_db, _ = resolve_paths(profile, db_path, None)
    conn = get_connection(resolved_db)
    init_db(conn)
    rows = list_session_checkpoints(conn, project_root=str(Path.cwd()), limit=50)
    if checkpoint_id is not None:
        rows = [r for r in rows if r["id"] == checkpoint_id]
    elif latest and rows:
        rows = rows[:1]
    if not rows:
        console.print("[dim]No checkpoint found.[/dim]")
        return
    payload = rows[0]["payload"]
    console.print(_checkpoint_content(payload))


@handoff_app.command(name="export")
def handoff_export(
    from_client: str = typer.Option(
        "unknown", "--from-client", help="Source AI client (e.g. cursor, claude-code)"
    ),
    to_client: Optional[str] = typer.Option(
        None, "--to-client", help="Target AI client (optional hint for the next session)"
    ),
    stdout: bool = typer.Option(
        False, "--stdout", help="Print markdown to stdout instead of writing files"
    ),
    profile: Optional[str] = typer.Option(None, "--profile", "-p", help="Target context profile"),
    db_path: Optional[Path] = typer.Option(None, "--db", help="Path to SQLite database"),
):
    """Exports a structured handoff artifact for switching AI tools."""
    from battery.config import get_active_profile
    from battery.handoff import export_handoff

    resolved_db, _ = resolve_paths(profile, db_path, None)
    conn = get_connection(resolved_db)
    init_db(conn)

    try:
        result = export_handoff(
            conn,
            project_root=Path.cwd(),
            profile=profile or get_active_profile(),
            from_client=from_client,
            to_client=to_client,
            stdout=stdout,
        )
        conn.commit()
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    if stdout:
        print(result["markdown"])
        return

    console.print(
        Panel.fit(
            f"[green]✓ Exported handoff[/green]\n"
            f"ID: [bold]{result['handoff_id'][:8]}[/bold]\n"
            f"JSON: [dim]{result['path']}[/dim]\n"
            f"Markdown: [dim]{result['markdown_path']}[/dim]\n"
            f"From: [cyan]{from_client}[/cyan]"
            + (f" → [cyan]{to_client}[/cyan]" if to_client else ""),
            title="Handoff Export",
        )
    )


@handoff_app.command(name="load")
def handoff_load(
    latest: bool = typer.Option(True, "--latest", help="Load the latest project handoff artifact"),
    file: Optional[Path] = typer.Option(None, "--file", help="Load a specific handoff JSON file"),
    ingest: bool = typer.Option(
        False, "--ingest", help="Also save the handoff as episodic memory in SQLite"
    ),
    to_client: Optional[str] = typer.Option(
        None, "--to-client", help="Client loading this handoff (for lineage metadata)"
    ),
    profile: Optional[str] = typer.Option(None, "--profile", "-p", help="Target context profile"),
    db_path: Optional[Path] = typer.Option(None, "--db", help="Path to SQLite database"),
    md_path: Optional[Path] = typer.Option(None, "--md", help="Path to living BATTERY.md mirror"),
):
    """Loads a handoff artifact as agent-ready markdown context."""
    from battery.handoff import load_handoff

    if not latest and file is None:
        console.print("[red]Specify --file or use --latest[/red]")
        raise typer.Exit(code=1)

    resolved_db, resolved_md = resolve_paths(profile, db_path, md_path)
    conn = get_connection(resolved_db)
    init_db(conn)

    try:
        result = load_handoff(
            conn,
            resolved_md,
            project_root=Path.cwd() if latest else None,
            file_path=file,
            ingest=ingest,
            to_client=to_client,
        )
        conn.commit()
    except FileNotFoundError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    if ingest and result.get("memory_id"):
        console.print(
            f"[green]✓ Ingested handoff as episodic memory #{result['memory_id']}[/green]"
        )

    console.print(result["markdown"])


@handoff_app.command(name="show")
def handoff_show(
    profile: Optional[str] = typer.Option(None, "--profile", "-p", help="Target context profile"),
    file: Optional[Path] = typer.Option(None, "--file", help="Show a specific handoff JSON file"),
):
    """Shows metadata for the latest handoff without loading into memory."""
    from battery.handoff import read_handoff_artifact

    try:
        artifact = read_handoff_artifact(project_root=Path.cwd(), file_path=file)
    except FileNotFoundError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    table = Table(title="Battery Handoff")
    table.add_column("Field", style="bold")
    table.add_column("Value")
    for key in (
        "handoff_id",
        "from_client",
        "to_client",
        "created_at",
        "verification_status",
        "checkpoint_id",
        "project_root",
    ):
        value = artifact.get(key)
        if value is not None:
            table.add_row(key, str(value))
    console.print(table)


def main():
    app()


if __name__ == "__main__":
    main()
