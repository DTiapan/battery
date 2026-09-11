"""Generates a scaled, realistic engineering dataset for stress-testing Battery Context Engine."""

import random
from typing import Any, Dict, List, Tuple

REALISTIC_CORPUS_SEED: List[Tuple[str, str, float]] = [
    # Rules
    (
        "Always use snake_case for Python function and variable names, and PascalCase for class names.",
        "rule",
        1.5,
    ),
    (
        "Git commit messages must strictly adhere to the Conventional Commits specification (e.g. feat:, fix:, docs:, chore:).",
        "rule",
        1.2,
    ),
    (
        "Security guideline: Never commit API keys, auth tokens, or plaintext credentials into git history.",
        "rule",
        1.5,
    ),
    (
        "All public Python library interfaces must include complete typing annotations compatible with mypy --strict.",
        "rule",
        1.3,
    ),
    (
        "Every database migration must be backward-compatible and include an explicit rollback procedure.",
        "rule",
        1.4,
    ),
    (
        "Never execute unbounded SELECT queries in production; always enforce explicit LIMIT clauses.",
        "rule",
        1.2,
    ),
    (
        "Go services must use errors.Is() and errors.As() instead of direct equality checks on error instances.",
        "rule",
        1.1,
    ),
    (
        "All HTTP endpoints returning paginated lists must support cursor-based pagination with limit and after parameters.",
        "rule",
        1.2,
    ),
    (
        "Unit tests must execute in under 100 milliseconds and never depend on external network services.",
        "rule",
        1.3,
    ),
    (
        "In Rust code, never call unwrap() in production paths; use the question mark operator or expect() with error context.",
        "rule",
        1.4,
    ),
    (
        "React functional components must use memo() only when profiling demonstrates measurable rendering bottlenecks.",
        "rule",
        1.0,
    ),
    (
        "Container images must run as a non-privileged user with UID 10001 and read-only root filesystems.",
        "rule",
        1.4,
    ),
    (
        "GraphQL mutations must return union types containing both the payload and structured user-facing errors.",
        "rule",
        1.1,
    ),
    (
        "All asynchronous message consumers must implement exponential backoff with jitter on transient failures.",
        "rule",
        1.3,
    ),
    (
        "TypeScript codebases must enforce noImplicitAny and strictNullChecks in tsconfig.json.",
        "rule",
        1.2,
    ),
    # Decisions
    (
        "Architecture Decision Record 0001: Adopt Markdown Architectural Decision Records (MADR) for engineering governance.",
        "decision",
        1.1,
    ),
    (
        "Architecture Decision Record 0002: Implement Python V1 prototype using uv, transitioning to Go 1.24+ for V2 daemon.",
        "decision",
        1.2,
    ),
    (
        "Architecture Decision Record 0003: Use SQLite in WAL mode with FTS5 and sqlite-vec for sovereign local storage substrate.",
        "decision",
        1.5,
    ),
    (
        "Architecture Decision Record 0004: Standardize on FastEmbed all-MiniLM-L6-v2 ONNX runtime producing 384-dimensional dense vectors.",
        "decision",
        1.4,
    ),
    (
        "Architecture Decision Record 0005: Maintain a bi-directional Markdown mirror in BATTERY.md synchronized via SQLite triggers.",
        "decision",
        1.3,
    ),
    (
        "Architecture Decision Record 0006: Adopt physical SQLite database partitioning for multi-battery context profile isolation.",
        "decision",
        1.4,
    ),
    (
        "Adopt Reciprocal Rank Fusion (RRF) with smoothing constant k=60 to fuse BM25 and vector search rankings.",
        "decision",
        1.3,
    ),
    (
        "Use Protobuf v3 for all internal service-to-service RPC contracts over gRPC HTTP/2 transport.",
        "decision",
        1.2,
    ),
    (
        "Standardize on OpenTelemetry SDK for distributed tracing, exporting OTLP payloads to Jaeger.",
        "decision",
        1.1,
    ),
    (
        "Deploy Kafka with Kraft mode enabled, deprecating ZooKeeper cluster dependencies.",
        "decision",
        1.3,
    ),
    (
        "Use Redis cluster with volatile-lru eviction policy for distributed session storage.",
        "decision",
        1.2,
    ),
    ("Standardize on Argon2id with 64MB memory cost for user password hashing.", "decision", 1.5),
    (
        "Use ClickHouse for high-throughput time-series event ingestion and analytical queries.",
        "decision",
        1.3,
    ),
    (
        "Implement Envoy proxy as sidecar for mutual TLS (mTLS) traffic encryption between Kubernetes pods.",
        "decision",
        1.2,
    ),
    (
        "Store binary assets in S3-compatible MinIO object storage with presigned download URLs.",
        "decision",
        1.1,
    ),
    # Preferences
    (
        "User prefers dark mode editor themes and high-contrast color palettes for code syntax highlighting.",
        "preference",
        1.2,
    ),
    (
        "Always produce concise, diff-focused explanations without conversational fluff, pleasantries, or preamble.",
        "preference",
        1.4,
    ),
    (
        "Format all markdown documentation with GitHub-flavored markdown alerts (NOTE, TIP, IMPORTANT, WARNING).",
        "preference",
        1.1,
    ),
    (
        "Developer prefers uv over poetry or pipenv for fast Python environment and package management.",
        "preference",
        1.2,
    ),
    (
        "Prefer functional programming patterns and pure functions over deeply nested object-oriented inheritance hierarchies.",
        "preference",
        1.0,
    ),
    (
        "Use conventional commit message prefixes feat, fix, docs, refactor, and chore.",
        "preference",
        1.1,
    ),
    (
        "Display latency metrics in milliseconds with p50, p95, and p99 percentiles in benchmark summaries.",
        "preference",
        1.2,
    ),
    (
        "Prefer explicit error handling with early returns over deeply indented try-catch blocks.",
        "preference",
        1.1,
    ),
    (
        "Terminal output should utilize Rich styling with distinct green checkmarks and cyan headers.",
        "preference",
        1.0,
    ),
    (
        "User prefers VS Code with Vim keybindings and 2-space indentation for JSON and YAML files.",
        "preference",
        1.1,
    ),
    # General
    (
        "Production PostgreSQL cluster operates on port 5432 with a read-replica running on port 5433.",
        "general",
        1.1,
    ),
    (
        "Staging Redis instance is accessible on redis-cluster.internal.net:6379 with TLS 1.3 enforced.",
        "general",
        1.0,
    ),
    (
        "Internal Kubernetes cluster runs on AWS EKS with Calico CNI and Cilium network policies.",
        "general",
        1.0,
    ),
    (
        "Production RabbitMQ broker is configured with cluster endpoint amqps://broker.prod.internal:5671.",
        "general",
        1.0,
    ),
    (
        "Monitoring Prometheus server scrapes metrics every 15 seconds from /metrics endpoints.",
        "general",
        0.9,
    ),
    (
        "Default API gateway timeout is configured to 30000 milliseconds for all ingress routes.",
        "general",
        1.0,
    ),
    (
        "Staging environment deploys to AWS eu-central-1 region using Terraform infrastructure-as-code.",
        "general",
        0.9,
    ),
    (
        "Elasticsearch logging cluster retains application logs for a rolling 14-day window before cold archival.",
        "general",
        1.0,
    ),
    (
        "Database connection pool is configured with max_connections=50 and idle_timeout=300 seconds.",
        "general",
        1.1,
    ),
    (
        "Authentication service issues RS256 signed JSON Web Tokens with a 15-minute expiration time.",
        "general",
        1.2,
    ),
]

# Variations and synthetic engineering patterns to scale up to 500 items
COMPONENTS = [
    "auth-service",
    "billing-worker",
    "search-indexer",
    "payment-gateway",
    "notification-dispatcher",
    "user-registry",
    "media-transcoder",
    "analytics-pipeline",
    "telemetry-collector",
    "rate-limiter",
]
TOPICS = [
    ("port", "operates on port {val} with health checks on /healthz"),
    ("timeout", "enforces a strict connection timeout of {val}ms for external RPC calls"),
    ("cache", "caches hot lookup responses in Redis with a TTL of {val} seconds"),
    ("concurrency", "configures worker pool concurrency to {val} worker threads"),
    ("retry", "implements exponential backoff with maximum {val} retry attempts"),
    ("memory", "sets Kubernetes container memory limits to {val}Mi with 250m CPU"),
    ("queue", "routes high-priority background tasks to Amazon SQS queue {val}"),
    ("circuit_breaker", "trips circuit breaker after {val} consecutive 5xx failure responses"),
    ("batch_size", "processes batch ingestion stream chunks in sizes of {val} records"),
    ("replica", "deploys across {val} availability zones with minimum replica count of 3"),
]


def generate_stress_corpus(target_size: int = 500) -> List[Dict[str, Any]]:
    """Generates a corpus of realistic technical memories up to target_size."""
    corpus: List[Dict[str, Any]] = []

    # 1. Add core seed items
    for idx, (content, category, importance) in enumerate(REALISTIC_CORPUS_SEED):
        corpus.append(
            {
                "id": idx + 1,
                "category": category,
                "importance": importance,
                "content": content,
            }
        )

    # 2. Synthesize structured realistic engineering items to fill remaining quota
    current_id = len(corpus) + 1
    random.seed(42)  # Deterministic generation
    seen_texts = {item["content"].strip() for item in corpus}

    categories = ["rule", "decision", "preference", "general"]
    while len(corpus) < target_size:
        comp = random.choice(COMPONENTS)
        topic, pattern = random.choice(TOPICS)
        val = (
            random.randint(1000, 9999)
            if "port" in topic or "timeout" in topic
            else random.randint(3, 500)
        )

        category = random.choice(categories)
        if category == "rule":
            text = f"Service rule for {comp}: {comp} {pattern.format(val=val)}."
        elif category == "decision":
            text = f"Architectural decision for {comp}: standardize on design where {comp} {pattern.format(val=val)}."
        elif category == "preference":
            text = f"Configuration preference: ensure {comp} {pattern.format(val=val)}."
        else:
            text = f"Operational parameter: {comp} {pattern.format(val=val)}."

        if text in seen_texts:
            continue
        seen_texts.add(text)

        corpus.append(
            {
                "id": current_id,
                "category": category,
                "importance": round(random.uniform(0.8, 1.4), 2),
                "content": text,
            }
        )
        current_id += 1

    return corpus


# 30 Challenging Benchmark Queries testing exact keyword, semantic intent, and hybrid
STRESS_QUERIES = [
    {
        "query": "What port does the PostgreSQL production database run on?",
        "type": "exact_keyword",
        "expected_ids": [41],
    },
    {
        "query": "What are the rules regarding secrets and credentials in version control?",
        "type": "exact_keyword",
        "expected_ids": [3],
    },
    {
        "query": "What embedding model and vector dimension are used?",
        "type": "exact_keyword",
        "expected_ids": [19],
    },
    {
        "query": "Where is the Redis cache located and which port does it use?",
        "type": "exact_keyword",
        "expected_ids": [42],
    },
    {
        "query": "How should git commit messages be formatted?",
        "type": "exact_keyword",
        "expected_ids": [2],
    },
    {
        "query": "What is the RabbitMQ broker endpoint URL and port?",
        "type": "exact_keyword",
        "expected_ids": [44],
    },
    {
        "query": "What is the token expiration duration for JSON Web Tokens?",
        "type": "exact_keyword",
        "expected_ids": [50],
    },
    {
        "query": "How should errors be wrapped in Go services?",
        "type": "exact_keyword",
        "expected_ids": [7],
    },
    {
        "query": "What password hashing algorithm and memory cost are standardized?",
        "type": "exact_keyword",
        "expected_ids": [27],
    },
    {
        "query": "What is the maximum number of connections configured in the database pool?",
        "type": "exact_keyword",
        "expected_ids": [49],
    },
    # Semantic Concept
    {
        "query": "How do we bridge state across different AI assistants without vendor lock-in?",
        "type": "semantic_concept",
        "expected_ids": [20],
    },
    {
        "query": "What are the styling and readability visual preferences of the developer?",
        "type": "semantic_concept",
        "expected_ids": [31],
    },
    {
        "query": "How should the AI communicate technical answers to the user?",
        "type": "semantic_concept",
        "expected_ids": [32],
    },
    {
        "query": "What is the ranking algorithm used for combining dense and sparse search scores?",
        "type": "semantic_concept",
        "expected_ids": [22],
    },
    {
        "query": "How are human-readable markdown notes kept in sync with the database?",
        "type": "semantic_concept",
        "expected_ids": [20],
    },
    {
        "query": "What guidelines govern writing clean backward-compatible database migrations?",
        "type": "semantic_concept",
        "expected_ids": [5],
    },
    {
        "query": "What are the security standards for running containers in Kubernetes?",
        "type": "semantic_concept",
        "expected_ids": [12],
    },
    {
        "query": "How are distributed traces exported and collected across microservices?",
        "type": "semantic_concept",
        "expected_ids": [24],
    },
    {
        "query": "What protocol is used for service-to-service communication?",
        "type": "semantic_concept",
        "expected_ids": [23],
    },
    {
        "query": "What is the retention strategy for log data before archival?",
        "type": "semantic_concept",
        "expected_ids": [48],
    },
    # Hybrid Technical
    {
        "query": "Which database engine and vector extension handle our persistent state?",
        "type": "hybrid_technical",
        "expected_ids": [18],
    },
    {
        "query": "What naming casing conventions apply to functions and classes in code?",
        "type": "hybrid_technical",
        "expected_ids": [1],
    },
    {
        "query": "What type checking standards are required for Python signatures?",
        "type": "hybrid_technical",
        "expected_ids": [4],
    },
    {
        "query": "What network security and container infrastructure is used for deployments?",
        "type": "hybrid_technical",
        "expected_ids": [43],
    },
    {
        "query": "What visual callout blocks should be used in technical docs?",
        "type": "hybrid_technical",
        "expected_ids": [33],
    },
    {
        "query": "What is our decision on multi-battery context profile isolation?",
        "type": "hybrid_technical",
        "expected_ids": [21],
    },
    {
        "query": "What tool is preferred for Python environment and package management?",
        "type": "hybrid_technical",
        "expected_ids": [34],
    },
    {
        "query": "What is the scrape frequency for Prometheus monitoring metrics?",
        "type": "hybrid_technical",
        "expected_ids": [45],
    },
    {
        "query": "How are unhandled exceptions avoided in production Rust code?",
        "type": "hybrid_technical",
        "expected_ids": [10],
    },
    {
        "query": "What is the global timeout for the API gateway ingress routes?",
        "type": "hybrid_technical",
        "expected_ids": [46],
    },
]


def get_stress_dataset(scale: int = 500) -> Dict[str, Any]:
    return {
        "corpus": generate_stress_corpus(target_size=scale),
        "queries": STRESS_QUERIES,
    }
