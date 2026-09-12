"""Real-world evaluation corpus extracted from Battery's own ADRs, README, and docstrings.

This is a dogfooding dataset: the memories are exactly the kind of content a developer using
Battery would store, and the queries are exactly what an LLM agent or developer would ask.
Ground truth is matched by content substring (not fragile integer IDs), making it future-proof.
"""

from typing import Any, Dict, List

# ---------------------------------------------------------------------------
# Real-world corpus — 100 genuine memories sourced from Battery's own artifacts
# Each item: (content, category, importance, ground_truth_tag)
# ground_truth_tag is a short unique substring used to identify this memory
# in evaluation without depending on row insertion order.
# ---------------------------------------------------------------------------
REALWORLD_CORPUS_RAW: List[tuple] = [
    # ── ADR 0001: Architecture Decisions Process ───────────────────────────
    (
        "Battery uses Architecture Decision Records (ADRs) stored in docs/adr/ numbered sequentially "
        "(0001-*.md, 0002-*.md) following the Michael Nygard / MADR standard to record major system decisions.",
        "decision",
        1.3,
        "ADR-process",
    ),
    (
        "Each ADR documents: Status (Proposed, Accepted, Deprecated, Superseded), Context, Decision Drivers, "
        "Considered Options with Pros/Cons, Decision and Rationale, and Consequences.",
        "rule",
        1.1,
        "ADR-structure",
    ),
    (
        "ADRs prevent architectural drift and ensure cross-model portability by keeping a clear audit trail "
        "of why specific systems primitives (Swiss Tables, W-TinyLFU, Merkle DAGs, Roaring Bitmaps) were "
        "borrowed or discarded.",
        "decision",
        1.2,
        "ADR-purpose",
    ),
    # ── ADR 0002: Phased Runtime Stack ─────────────────────────────────────
    (
        "Battery V1 is implemented in Python 3.12+ using uv for rapid validation of hybrid retrieval "
        "algorithms, local embedding pipelines, and Model Context Protocol tool interfaces.",
        "decision",
        1.3,
        "V1-python",
    ),
    (
        "Battery V2 production target is a single statically-linked Go 1.24+ binary with under 5ms cold "
        "start and under 30MB baseline RAM, running over a Unix Domain Socket (battery.sock).",
        "decision",
        1.4,
        "V2-go-daemon",
    ),
    (
        "The two-phase implementation strategy (Python V1 → Go V2) allows algorithmic validation of RRF "
        "fusion constants, vector similarity thresholds, and tokenizer portability across Claude, Gemini, "
        "and Cursor before committing to binary ABIs.",
        "decision",
        1.2,
        "phased-strategy",
    ),
    # ── ADR 0003: Storage Substrate ────────────────────────────────────────
    (
        "Battery uses SQLite in WAL mode (PRAGMA journal_mode=WAL) with FTS5 for BM25 keyword search "
        "and sqlite-vec for float32 vector similarity as its primary storage substrate. No external "
        "database daemons are required.",
        "decision",
        1.5,
        "sqlite-wal-fts5-vec",
    ),
    (
        "SQLite WAL mode (Write-Ahead Logging) enables concurrent readers without blocking writes, "
        "providing ACID transaction guarantees and crash resilience on power loss.",
        "decision",
        1.3,
        "wal-concurrency",
    ),
    (
        "Battery SQLite pragmas: journal_mode=WAL, synchronous=NORMAL, busy_timeout=5000, "
        "foreign_keys=ON. These settings balance durability, performance, and concurrency safety.",
        "rule",
        1.4,
        "sqlite-pragmas",
    ),
    (
        "Battery rejected specialized vector databases (DuckDB, LanceDB, Chroma) because they have "
        "weaker full-text tokenization and higher dependency weight compared to SQLite with sqlite-vec.",
        "decision",
        1.1,
        "rejected-vectordbs",
    ),
    (
        "Battery rejected pure key-value stores (BadgerDB, RocksDB) because they require implementing "
        "custom B-tree indexing, secondary indexes, and text tokenization from scratch.",
        "decision",
        1.1,
        "rejected-kvstores",
    ),
    (
        "Content deduplication uses SHA-256 hashing of the memory text to prevent redundant duplicate "
        "memories across multiple LLM turns. The content_hash column has a UNIQUE constraint.",
        "rule",
        1.3,
        "sha256-dedup",
    ),
    (
        "Battery's hybrid retrieval scoring formula: RRF_Score(d) = (w_text / (k + rank_bm25(d))) + "
        "(w_vec / (60 + rank_vec(d))), where k=60, w_text=0.5, w_vec=0.5 by default.",
        "decision",
        1.5,
        "rrf-formula",
    ),
    (
        "Single-file SQLite storage means battery.db is readable and inspectable by any tool on earth. "
        "Backup is a simple file copy. Migration uses standard sqlite3 .dump format.",
        "decision",
        1.2,
        "single-file-portability",
    ),
    # ── ADR 0004: Embedding Strategy ───────────────────────────────────────
    (
        "Battery uses sentence-transformers/all-MiniLM-L6-v2 as its default embedding model, "
        "producing 384-dimensional normalized float32 vectors via the fastembed ONNX runtime.",
        "decision",
        1.5,
        "miniLM-384-onnx",
    ),
    (
        "Battery embedding performance: approximately 12ms per embedding on consumer laptop CPUs "
        "using fastembed with AVX2/NEON SIMD acceleration. No GPU required.",
        "decision",
        1.4,
        "embedding-12ms-cpu",
    ),
    (
        "Battery model weights: all-MiniLM-L6-v2 is approximately 90MB, cached locally in "
        "~/.battery/models/ after first download. Zero API costs. 100% offline.",
        "decision",
        1.3,
        "model-90mb-offline",
    ),
    (
        "Battery rejects external cloud embedding APIs (OpenAI, Cohere) because they introduce "
        "100–300ms network latency, API key management friction, and violate local sovereignty.",
        "decision",
        1.4,
        "reject-cloud-embeddings",
    ),
    (
        "Battery rejects heavy PyTorch/Transformers pipelines because they introduce over 2GB "
        "dependency footprint and multi-second process startup delays.",
        "decision",
        1.3,
        "reject-pytorch",
    ),
    (
        "Battery vector dimension is fixed at 384. Changing to a different dimension model requires "
        "re-indexing all existing memories. This is a known architectural trade-off.",
        "decision",
        1.2,
        "384-dim-tradeoff",
    ),
    (
        "Battery vector storage: vec_memories virtual table using sqlite-vec float[384] schema. "
        "Compact footprint: 10,000 memories = approximately 15MB of vector data in SQLite.",
        "decision",
        1.3,
        "vec-storage-footprint",
    ),
    # ── ADR 0005: MCP Interface & Living Mirror ─────────────────────────────
    (
        "Battery exposes four MCP tools over Stdio transport: recall_memory(query, limit, category), "
        "save_memory(content, category, importance), list_memories(category, limit), "
        "forget_memory(memory_id).",
        "decision",
        1.5,
        "mcp-four-tools",
    ),
    (
        "Battery MCP server communicates over standard Stdio (stdin/stdout) using JSON-RPC, "
        "making it compatible with any MCP 2.x compliant client including Claude Desktop, "
        "Cursor IDE, and Gemini CLI.",
        "decision",
        1.4,
        "mcp-stdio-jsonrpc",
    ),
    (
        "The BATTERY.md Living Mirror pattern: when a memory is saved to SQLite, the engine "
        "immediately writes an atomic human-readable BATTERY.md file grouped by categories "
        "(Rules, Decisions, Preferences). Developers inspect what the AI agent stored by "
        "reading BATTERY.md in the IDE or repo — no SQL queries required. This file is git-committable.",
        "decision",
        1.4,
        "battery-md-mirror",
    ),
    (
        "BATTERY.md bidirectional sync: editing BATTERY.md directly and running 'battery sync' "
        "causes the engine to detect diffs, re-embed changes, and update SQLite. "
        "SHA-256 hashing distinguishes agent-generated writes from human edits.",
        "rule",
        1.3,
        "battery-md-sync",
    ),
    (
        "Battery rejected opaque database-only storage (REST/CLI with no workspace artifact) "
        "because memory is trapped in a black box — no git-diffable file for humans to audit "
        "what the LLM remembered.",
        "decision",
        1.1,
        "reject-opaque-db",
    ),
    (
        "Teammates cloning a repository that contains BATTERY.md inherit project memory instantly. "
        "Pull requests can review changes to project architectural rules.",
        "decision",
        1.2,
        "team-memory-sharing",
    ),
    # ── ADR 0006: Multi-Battery Context Profiles ───────────────────────────
    (
        "Battery context profiles keep separate memories for different client projects: each profile "
        "has its own independent SQLite file at ~/.battery/profiles/<profile>/battery.db with "
        "its own FTS5 index and vec0 table. Switch active context with `battery use <profile>`.",
        "decision",
        1.4,
        "physical-profile-isolation",
    ),
    (
        "Battery profile path resolution hierarchy: (1) --db flag, (2) BATTERY_DB_PATH env, "
        "(3) --profile flag, (4) BATTERY_PROFILE env, (5) ~/.battery/current_profile file, "
        "(6) default (~/.battery/battery.db).",
        "rule",
        1.3,
        "profile-path-resolution",
    ),
    (
        "Battery rejected logical partitioning (single database with profile column) because it risks "
        "cross-tenant data leaks if a query omits the WHERE profile = ? clause, and degrades "
        "vector search precision when unrelated domains share the embedding index.",
        "decision",
        1.2,
        "rejected-logical-partitioning",
    ),
    (
        "Battery profile CLI commands: 'battery profile list', 'battery profile create <name>', "
        "'battery use <name>' (shorthand for switch), 'battery profile current', "
        "'battery profile delete <name>'.",
        "rule",
        1.2,
        "profile-cli-commands",
    ),
    (
        "Battery context profiles solve cross-project collision: a rule like 'Use PostgreSQL on port 5432' "
        "for a backend microservice must not pollute prompts when working on a React Native mobile frontend.",
        "decision",
        1.3,
        "cross-project-collision",
    ),
    # ── Core Philosophy & System Design ────────────────────────────────────
    (
        "Battery's core philosophy: LLMs are commodity compute; your domain context, architectural "
        "decisions, and project rules are the sovereign asset. Context is treated as a rechargeable, "
        "portable, git-committable battery pack.",
        "decision",
        1.5,
        "core-philosophy",
    ),
    (
        "The Model Switch Tax problem: every time a developer switches between Claude, Cursor, and Gemini, "
        "they re-explain tech stack decisions, naming conventions, and constraints from scratch. "
        "Battery eliminates this by maintaining persistent cross-tool context.",
        "decision",
        1.4,
        "model-switch-tax",
    ),
    (
        "Battery runs locally with zero external database daemons, calls zero cloud embedding APIs, "
        "and plugs into any AI assistant via the open Model Context Protocol (MCP).",
        "decision",
        1.5,
        "zero-external-deps",
    ),
    (
        "The Static Workaround Failure: static files like CLAUDE.md or .cursorrules quickly become "
        "outdated, cannot be searched semantically, and bloat the LLM context window on every prompt.",
        "decision",
        1.3,
        "static-file-failure",
    ),
    (
        "Cloud-hosted memory engines like ChatGPT Memory lock proprietary architectural decisions in "
        "third-party servers with opaque recall heuristics, subscription costs, and vendor lock-in.",
        "decision",
        1.3,
        "cloud-memory-lockin",
    ),
    # ── Hybrid Retrieval Design ─────────────────────────────────────────────
    (
        "Vector failure mode: high-dimensional embeddings smear exact technical tokens. "
        "Searching for 'port 5432', 'PRAGMA journal_mode', or 'handle_auth_callback' via cosine "
        "similarity often returns conceptually related but factually incorrect chunks.",
        "decision",
        1.4,
        "vector-failure-mode",
    ),
    (
        "BM25 keyword failure mode: traditional BM25 completely misses semantic intent. A query like "
        "'how do we handle database replication?' fails if the memory only mentions "
        "'WAL streaming to replica nodes'.",
        "decision",
        1.4,
        "bm25-failure-mode",
    ),
    (
        "Reciprocal Rank Fusion (RRF) fuses ranked lists from BM25 and vector search. "
        "The formula guarantees exact code tokens surface to Rank #1 while conceptual queries "
        "still achieve maximum recall through the vector component.",
        "decision",
        1.5,
        "rrf-guarantees",
    ),
    (
        "Battery's hybrid retrieval runs both BM25 and vector searches simultaneously against SQLite, "
        "then merges the ranked lists using RRF. The candidate pool is top-50 from each method before fusion.",
        "rule",
        1.3,
        "hybrid-candidate-pool-50",
    ),
    (
        "Battery FTS5 query sanitization removes stop words, tokenizes on word boundaries, and uses "
        'OR-matching with prefix wildcards (e.g., "token"*) to maximize BM25 recall on partial terms.',
        "rule",
        1.2,
        "fts5-sanitization",
    ),
    # ── Memory Categories & Data Model ─────────────────────────────────────
    (
        "Battery memory categories: 'rule' (coding standards, constraints), 'decision' (architectural "
        "choices, ADRs), 'preference' (developer habits, tool choices), 'general' (operational facts, "
        "endpoints, configuration parameters).",
        "rule",
        1.3,
        "memory-categories",
    ),
    (
        "Battery memories table columns: id (INTEGER PK), content_hash (UNIQUE SHA-256), content (TEXT), "
        "category (TEXT), importance (REAL default 1.0), created_at (ISO-8601), updated_at, "
        "is_deleted (INTEGER 0/1 tombstone flag).",
        "rule",
        1.2,
        "memories-schema",
    ),
    (
        "Battery uses tombstoning instead of hard DELETE for memory removal. is_deleted=1 preserves "
        "the audit trail and allows restoration. The vec_memories entry IS deleted on tombstone "
        "to prevent ghost matches in vector search.",
        "rule",
        1.3,
        "tombstone-pattern",
    ),
    (
        "Battery importance field: a float multiplier (default 1.0) on the memory's weight. "
        "Higher importance memories should surface preferentially in retrieval. "
        "Currently stored but not yet factored into RRF scoring.",
        "rule",
        1.2,
        "importance-field",
    ),
    # ── CLI Commands ────────────────────────────────────────────────────────
    (
        "Battery CLI commands: 'battery init' (scaffold DB and BATTERY.md), 'battery add' (save memory), "
        "'battery query' (hybrid search), 'battery list' (browse memories), 'battery forget' (tombstone), "
        "'battery sync' (sync BATTERY.md to SQLite), 'battery serve' (start MCP server).",
        "rule",
        1.3,
        "cli-commands",
    ),
    (
        "Battery setup command: 'battery setup --client all' automatically writes the MCP server "
        "configuration to Claude Desktop's claude_desktop_config.json and Cursor's config. "
        "It requires the 'battery' binary to be on PATH.",
        "rule",
        1.2,
        "setup-command",
    ),
    (
        "Battery eval command: 'battery eval' runs the standard 15-query retrieval benchmark. "
        "'battery eval --stress' runs the 500-item scaled stress test. "
        "'battery eval --tune' runs the RRF k/weight grid sweep.",
        "rule",
        1.2,
        "eval-command",
    ),
    # ── Engineering Rules & Coding Standards ───────────────────────────────
    (
        "All Python code in Battery must include strict type annotations compatible with mypy --strict "
        "and PEP 257 docstrings on all public functions and classes.",
        "rule",
        1.4,
        "python-typing-docstrings",
    ),
    (
        "Battery uses uv as the Python package and environment manager. Install dependencies with "
        "'uv sync'. Run tools with 'uv run <command>'. Do not use pip, poetry, or pipenv.",
        "preference",
        1.4,
        "uv-package-manager",
    ),
    (
        "Battery uses Ruff for linting and formatting. Run 'uv run ruff format src tests' and "
        "'uv run ruff check src tests' before every commit. All code must pass with zero errors.",
        "rule",
        1.5,
        "ruff-linting",
    ),
    (
        "Git commit messages must follow Conventional Commits: feat:, fix:, docs:, test:, refactor:, "
        "chore:. All commits must be authored as DTiapan <bakran.ajas@gmail.com>.",
        "rule",
        1.5,
        "conventional-commits",
    ),
    (
        "Battery uses pytest for testing. Run 'uv run pytest -v'. All tests must pass before pushing. "
        "Tests must not depend on external network services or cloud APIs.",
        "rule",
        1.4,
        "pytest-testing",
    ),
    (
        "Battery follows a zero-bloat philosophy: keep the engine lean, fast, and local-first. "
        "Avoid unnecessary feature bloat or heavy background daemons. Every new dependency must be justified.",
        "preference",
        1.5,
        "zero-bloat",
    ),
    # ── Performance Targets & Benchmarks ───────────────────────────────────
    (
        "Battery retrieval latency target: p50 under 20ms, p95 under 50ms for hybrid search across "
        "up to 500 memories. This is imperceptible to LLMs which add 500ms–3000ms per API call.",
        "decision",
        1.4,
        "latency-target-20ms",
    ),
    (
        "Battery disk footprint: 500 memories (raw text + FTS5 inverted index + 384-dim float32 vectors) "
        "fits in under 2MB SQLite file. 10,000 memories would require approximately 40MB.",
        "decision",
        1.3,
        "disk-footprint-2mb",
    ),
    (
        "Battery batch ingestion throughput measured at 55–75 items/sec on MacBook CPU using ONNX "
        "fastembed. The bottleneck is local ONNX model inference, not SQLite writes.",
        "decision",
        1.2,
        "ingestion-throughput",
    ),
    (
        "Battery cold-start latency for 'battery query' is under 2 seconds on first run (ONNX model "
        "load from disk). Subsequent calls are sub-15ms because the ONNX model stays resident.",
        "decision",
        1.3,
        "cold-start-latency",
    ),
    # ── Real Engineering Rules (Curated) ───────────────────────────────────
    (
        "Never commit API keys, auth tokens, or plaintext credentials into git history. "
        "Use environment variables or secrets managers (AWS Secrets Manager, HashiCorp Vault).",
        "rule",
        1.5,
        "no-secrets-in-git",
    ),
    (
        "All database migrations must be backward-compatible and include an explicit rollback procedure. "
        "Test rollbacks in staging before applying to production.",
        "rule",
        1.4,
        "backward-compat-migrations",
    ),
    (
        "Never execute unbounded SELECT queries in production. Always enforce explicit LIMIT clauses "
        "and use cursor-based pagination for large result sets.",
        "rule",
        1.4,
        "bounded-queries",
    ),
    (
        "Unit tests must execute in under 100 milliseconds and must never depend on external network "
        "services, live databases, or cloud APIs. Use fixtures and mocks for external dependencies.",
        "rule",
        1.3,
        "fast-unit-tests",
    ),
    (
        "All asynchronous message consumers must implement exponential backoff with jitter on transient "
        "failures to prevent thundering herd during downstream service recovery.",
        "rule",
        1.3,
        "exponential-backoff-jitter",
    ),
    (
        "Container images must run as a non-privileged user (UID > 999) with read-only root filesystems. "
        "Never run production containers as root.",
        "rule",
        1.4,
        "container-non-root",
    ),
    (
        "HTTP APIs returning paginated lists must support cursor-based pagination with 'limit' and "
        "'after' parameters. Offset-based pagination degrades at large offsets.",
        "rule",
        1.2,
        "cursor-pagination",
    ),
    (
        "Standardize on Argon2id with at least 64MB memory cost for user password hashing. "
        "bcrypt is acceptable but Argon2id is the modern recommendation per OWASP 2024.",
        "rule",
        1.3,
        "argon2id-passwords",
    ),
    (
        "Use OpenTelemetry SDK for distributed tracing across microservices. "
        "Export OTLP payloads to a Jaeger or Grafana Tempo collector. "
        "Always propagate W3C trace context headers.",
        "rule",
        1.2,
        "opentelemetry-tracing",
    ),
    (
        "Go services must use errors.Is() and errors.As() for error type checking. "
        "Never use direct equality checks on error instances. Wrap errors with fmt.Errorf('%w', err).",
        "rule",
        1.3,
        "go-error-wrapping",
    ),
    (
        "In Rust production code, never call .unwrap() in non-test paths. "
        "Use the ? operator for error propagation or .expect() with a descriptive error message.",
        "rule",
        1.4,
        "rust-no-unwrap",
    ),
    (
        "TypeScript projects must enable noImplicitAny and strictNullChecks in tsconfig.json. "
        "Use strict mode to enable all strict type-checking options.",
        "rule",
        1.3,
        "typescript-strict",
    ),
    (
        "Redis cluster configuration: use volatile-lru eviction policy for session caches "
        "and allkeys-lru for general-purpose caches. Never use noeviction on shared clusters.",
        "rule",
        1.2,
        "redis-eviction-policy",
    ),
    (
        "Database connection pool settings: max_connections=50, idle_timeout=300 seconds, "
        "connection_timeout=5 seconds. Monitor pool exhaustion as a leading indicator of service overload.",
        "rule",
        1.2,
        "db-connection-pool",
    ),
    (
        "Prometheus scrapes metrics every 15 seconds from /metrics endpoints by default. "
        "Alert on p99 latency exceeding SLA thresholds. Use Grafana for dashboards.",
        "rule",
        1.1,
        "prometheus-monitoring",
    ),
    (
        "Authentication service issues RS256-signed JSON Web Tokens (JWTs) with 15-minute expiration. "
        "Use refresh tokens with 7-day sliding window expiration for extended sessions.",
        "rule",
        1.3,
        "jwt-rs256-15min",
    ),
    # ── Developer Preferences ───────────────────────────────────────────────
    (
        "Prefer functional programming patterns and pure functions over deeply nested object-oriented "
        "inheritance hierarchies. Favor composition over inheritance.",
        "preference",
        1.2,
        "functional-programming",
    ),
    (
        "Prefer explicit error handling with early returns (guard clauses) over deeply nested "
        "try-catch blocks or conditional nesting.",
        "preference",
        1.2,
        "early-returns",
    ),
    (
        "Terminal output should use Rich library styling with distinct green checkmarks for success, "
        "cyan for progress headers, red for errors, and yellow for warnings.",
        "preference",
        1.1,
        "rich-terminal-styling",
    ),
    (
        "Produce concise, diff-focused explanations without conversational fluff, pleasantries, or "
        "preamble. Start responses directly with the answer or code change.",
        "preference",
        1.4,
        "concise-explanations",
    ),
    (
        "Format all markdown documentation using GitHub-flavored markdown alerts: NOTE for context, "
        "TIP for suggestions, IMPORTANT for critical requirements, WARNING for breaking changes, "
        "CAUTION for high-risk operations.",
        "preference",
        1.2,
        "gfm-alerts",
    ),
    (
        "Developer uses uv over poetry or pipenv for Python environment management. "
        "Developer prefers dark mode editor themes and VS Code with Vim keybindings.",
        "preference",
        1.1,
        "dev-tools-preferences",
    ),
    (
        "Display latency metrics in milliseconds with p50, p95, and p99 percentiles in benchmark "
        "summaries. Never report averages without also showing the tail latencies.",
        "preference",
        1.3,
        "latency-percentiles",
    ),
    # ── Operational & Infrastructure ───────────────────────────────────────
    (
        "Production PostgreSQL cluster: primary on port 5432, read-replica on port 5433. "
        "Always route read-heavy analytical queries to the replica.",
        "general",
        1.2,
        "postgres-ports",
    ),
    (
        "Staging environment deploys to AWS eu-central-1 region using Terraform. "
        "Production is in us-east-1 with multi-AZ deployment and automatic failover.",
        "general",
        1.1,
        "aws-regions",
    ),
    (
        "API gateway global timeout: 30,000 milliseconds (30 seconds) for all ingress routes. "
        "Individual service timeouts must be lower than this to allow graceful error propagation.",
        "general",
        1.2,
        "api-gateway-timeout-30s",
    ),
    (
        "Elasticsearch logging cluster: retains application logs for a rolling 14-day window, "
        "then cold-archives to S3 Glacier. Set ILM policy with hot/warm/cold/delete phases.",
        "general",
        1.1,
        "elasticsearch-log-retention",
    ),
    (
        "Staging Redis is accessible at redis-cluster.internal.net:6379 with TLS 1.3 required. "
        "Production Redis cluster uses sentinel-based failover with three replicas.",
        "general",
        1.1,
        "redis-endpoints",
    ),
    (
        "Kubernetes cluster uses AWS EKS with Calico CNI for network policy enforcement. "
        "All cross-namespace traffic is denied by default and must be explicitly allowed via NetworkPolicy.",
        "general",
        1.2,
        "kubernetes-eks-calico",
    ),
    (
        "Binary assets and user-uploaded media are stored in S3-compatible MinIO object storage. "
        "Use presigned download URLs with 15-minute expiration. Never serve binary assets directly from EC2.",
        "general",
        1.1,
        "minio-object-storage",
    ),
    # ── Battery Evaluation & Quality ───────────────────────────────────────
    (
        "Battery evaluation harness compares BM25 (FTS5), Dense Vector (sqlite-vec), and Battery Hybrid "
        "(RRF) using Hit@1, Hit@3, Hit@5, and MRR (Mean Reciprocal Rank) metrics across 15 golden queries.",
        "decision",
        1.3,
        "eval-metrics",
    ),
    (
        "Battery stress test: 500 realistic engineering memories evaluated against 30 technical queries "
        "across exact_keyword, semantic_concept, and hybrid_technical query types. "
        "Measures throughput, latency distribution, and retrieval recall under load.",
        "decision",
        1.2,
        "stress-test-spec",
    ),
    (
        "Battery evaluation ground truth is matched by content substring (ground_truth_tag), "
        "not by fragile integer row IDs. This makes the benchmark future-proof across insertions and re-seedings.",
        "rule",
        1.2,
        "eval-ground-truth",
    ),
]


def build_realworld_corpus() -> List[Dict[str, Any]]:
    """Builds the real-world evaluation corpus from Battery's own artifacts."""
    corpus = []
    for idx, (content, category, importance, tag) in enumerate(REALWORLD_CORPUS_RAW):
        corpus.append(
            {
                "id": idx + 1,
                "content": content,
                "category": category,
                "importance": importance,
                "ground_truth_tag": tag,
            }
        )
    return corpus


# ---------------------------------------------------------------------------
# 30 Real Developer / LLM-Agent Queries with ground truth tags
# These mirror exactly what a developer or Claude/Cursor would ask Battery.
# ---------------------------------------------------------------------------
REALWORLD_QUERIES: List[Dict[str, Any]] = [
    # ── Exact Technical / Keyword ──────────────────────────────────────────
    {
        "query": "What embedding model does Battery use and what dimension are the vectors?",
        "type": "exact_keyword",
        "expected_tags": ["miniLM-384-onnx"],
    },
    {
        "query": "What port does the PostgreSQL production database run on?",
        "type": "exact_keyword",
        "expected_tags": ["postgres-ports"],
    },
    {
        "query": "What are the SQLite PRAGMA settings Battery configures on startup?",
        "type": "exact_keyword",
        "expected_tags": ["sqlite-pragmas"],
    },
    {
        "query": "What is the JWT expiration duration and signing algorithm?",
        "type": "exact_keyword",
        "expected_tags": ["jwt-rs256-15min"],
    },
    {
        "query": "What password hashing algorithm should be used and what is the memory cost?",
        "type": "exact_keyword",
        "expected_tags": ["argon2id-passwords"],
    },
    {
        "query": "What are the database connection pool settings for max connections and idle timeout?",
        "type": "exact_keyword",
        "expected_tags": ["db-connection-pool"],
    },
    {
        "query": "What is the global API gateway timeout in milliseconds?",
        "type": "exact_keyword",
        "expected_tags": ["api-gateway-timeout-30s"],
    },
    {
        "query": "What are the four MCP tools Battery exposes to AI agents?",
        "type": "exact_keyword",
        "expected_tags": ["mcp-four-tools"],
    },
    {
        "query": "What Go version is targeted for the Battery V2 production daemon?",
        "type": "exact_keyword",
        "expected_tags": ["V2-go-daemon"],
    },
    {
        "query": "How many megabytes are the ONNX model weights that Battery downloads?",
        "type": "exact_keyword",
        "expected_tags": ["model-90mb-offline"],
    },
    # ── Semantic Concept ───────────────────────────────────────────────────
    {
        "query": "How does Battery prevent the same memory from being stored twice?",
        "type": "semantic_concept",
        "expected_tags": ["sha256-dedup"],
    },
    {
        "query": "Why did Battery choose not to use cloud embedding services?",
        "type": "semantic_concept",
        "expected_tags": ["reject-cloud-embeddings"],
    },
    {
        "query": "How do teammates share project context and memory across different machines?",
        "type": "semantic_concept",
        "expected_tags": ["team-memory-sharing"],
    },
    {
        "query": "What happens to a memory when it is deleted? Is it permanently removed?",
        "type": "semantic_concept",
        "expected_tags": ["tombstone-pattern"],
    },
    {
        "query": "How can a developer inspect what the AI agent stored without running SQL?",
        "type": "semantic_concept",
        "expected_tags": ["battery-md-mirror"],
    },
    {
        "query": "What is the problem with keeping context in static .cursorrules or CLAUDE.md files?",
        "type": "semantic_concept",
        "expected_tags": ["static-file-failure"],
    },
    {
        "query": "How does Battery allow developers to keep separate memories for different client projects?",
        "type": "semantic_concept",
        "expected_tags": ["physical-profile-isolation"],
    },
    {
        "query": "What does the Battery core philosophy say about who owns the context?",
        "type": "semantic_concept",
        "expected_tags": ["core-philosophy"],
    },
    {
        "query": "How do logs get archived after the retention window expires?",
        "type": "semantic_concept",
        "expected_tags": ["elasticsearch-log-retention"],
    },
    {
        "query": "What are the risks of using a single shared database for multiple projects?",
        "type": "semantic_concept",
        "expected_tags": ["rejected-logical-partitioning"],
    },
    # ── Hybrid Technical ───────────────────────────────────────────────────
    {
        "query": "Which storage engine and vector extension does Battery use for retrieval?",
        "type": "hybrid_technical",
        "expected_tags": ["sqlite-wal-fts5-vec"],
    },
    {
        "query": "What ranking algorithm fuses BM25 and vector scores in Battery?",
        "type": "hybrid_technical",
        "expected_tags": ["rrf-formula"],
    },
    {
        "query": "What tool does Battery use for code linting and formatting?",
        "type": "hybrid_technical",
        "expected_tags": ["ruff-linting"],
    },
    {
        "query": "Why does Battery use SQLite instead of a dedicated vector database?",
        "type": "hybrid_technical",
        "expected_tags": ["rejected-vectordbs"],
    },
    {
        "query": "What CPU inference latency does Battery achieve for embedding computation?",
        "type": "hybrid_technical",
        "expected_tags": ["embedding-12ms-cpu"],
    },
    {
        "query": "How does Battery handle errors in vector search when a keyword has no FTS5 match?",
        "type": "hybrid_technical",
        "expected_tags": ["hybrid-candidate-pool-50"],
    },
    {
        "query": "What Python version and package manager are used for Battery development?",
        "type": "hybrid_technical",
        "expected_tags": ["uv-package-manager"],
    },
    {
        "query": "What network security model is used for inter-service traffic in Kubernetes?",
        "type": "hybrid_technical",
        "expected_tags": ["kubernetes-eks-calico"],
    },
    {
        "query": "What coding language and runtime will the production Battery V2 daemon be written in?",
        "type": "hybrid_technical",
        "expected_tags": ["V2-go-daemon"],
    },
    {
        "query": "What is the retrieval latency target for Battery and how does it compare to LLM API latency?",
        "type": "hybrid_technical",
        "expected_tags": ["latency-target-20ms"],
    },
]


def get_realworld_dataset() -> Dict[str, Any]:
    """Returns the real-world corpus and query set for evaluation."""
    corpus = build_realworld_corpus()
    # Build a tag→content lookup for ground truth matching
    tag_to_content: Dict[str, str] = {item["ground_truth_tag"]: item["content"] for item in corpus}
    return {
        "corpus": corpus,
        "queries": REALWORLD_QUERIES,
        "tag_to_content": tag_to_content,
    }
