# ADR 0006: Multi-Battery Context Profiles and Memory Isolation

## Status
Accepted

## Date
2026-09-11

## Context
As developers and AI agents move between projects, repositories, and domains, storing all memories, rules, and architectural decisions inside a single global SQLite database (`~/.battery/battery.db`) causes context contamination:
1. **Cross-Project Collision:** Rules intended for a backend microservice (e.g., "Use PostgreSQL on port 5432") can pollute prompts when the user works on a mobile frontend app (e.g., React Native).
2. **Client Scope Separation:** Enterprise consulting or client-specific conventions must remain strictly partitioned to prevent confidential business logic or API parameters from leaking across context boundaries.
3. **Ergonomic Switching:** Developers need an instantaneous, zero-latency mechanism to switch active context profiles (`battery use <name>`) without modifying configuration files by hand.

## Decision Drivers
* **Strict Physical Isolation:** Separate projects must have independent SQLite database files and `BATTERY.md` mirrors on disk.
* **Backwards Compatibility:** The `"default"` profile must transparently map to the existing `~/.battery/battery.db` without breaking legacy setups.
* **Developer Ergonomics:** Support both a persistent global switch (`battery use <profile>`) and per-command overrides (`--profile <profile>`).
* **MCP Integration:** Allow MCP clients (Claude Desktop, Cursor) to connect either to the globally active profile or a dedicated profile server (`battery serve --profile <profile>`).

## Considered Options

### Option 1: Logical Partitioning (Single Database with `profile` Column)
* **Pros:** Single database file; trivial schema extension.
* **Cons:** Risk of cross-tenant data leaks if a query omits the `WHERE profile = ?` clause; large vector index shared across unrelated domains degrades cosine search precision.

### Option 2: Physical Database Partitioning per Profile (Multi-Battery Substrates)
* **Pros:**
  * Complete physical isolation: each profile has its own independent SQLite database file (`~/.battery/profiles/<profile>/battery.db`) with its own FTS5 index and `vec0` vector table.
  * Deleting or archiving a project is as simple as removing its directory.
  * Vector search remains fast and hyper-relevant because the embedding index only contains domain-specific knowledge.
* **Cons:** Requires profile directory management and path resolution logic.

## Decision
We adopt **Option 2: Physical Database Partitioning per Profile**.

1. **Directory Layout:**
   ```text
   ~/.battery/
   ├── battery.db                  # 'default' profile database (backwards-compatible)
   ├── current_profile             # Contains active profile name (e.g., 'backend-api')
   └── profiles/
       ├── backend-api/
       │   └── battery.db          # Isolated database for backend-api
       └── mobile-client/
           └── battery.db          # Isolated database for mobile-client
   ```

2. **Path Resolution Hierarchy:**
   - Database path is resolved via:
     1. Explicit `--db <path>` flag.
     2. `BATTERY_DB_PATH` environment variable.
     3. `--profile <name>` flag if supplied.
     4. `BATTERY_PROFILE` environment variable if defined.
     5. `~/.battery/current_profile` content.
     6. Defaults to `"default"` (`~/.battery/battery.db`).

3. **CLI Interface:**
   - `battery profile list`: Lists all profiles, database paths, and active indicators.
   - `battery profile create <name>`: Initializes an isolated profile.
   - `battery profile switch <name>` / `battery use <name>`: Switches the system-wide active profile.
   - `battery profile current`: Displays active profile name and path.
   - `battery profile delete <name>`: Purges a profile and its SQLite storage.

## Consequences

### Positive
* Zero chance of accidental context leaks between disparate codebases.
* Sub-15ms vector queries remain lean because indexes are compact and domain-focused.
* Fully backward compatible with Battery v0.1.0 installations.

### Negative
* Cross-profile queries (searching across all profiles simultaneously) require explicit tooling in future releases.
