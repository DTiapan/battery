# ADR 0003: Storage Substrate and Hybrid Retrieval Engine

## Status
Accepted

## Date
2026-09-11

## Context
The Battery Context Engine must store user context, agent decisions, rules, and episodic interactions locally with zero external database dependencies. It must support high-precision lookups (exact keyword matches, e.g. "PostgreSQL port", "API key env var") as well as semantic similarity queries (e.g. "what did we decide about database replication?").

Relying solely on vector search results in poor precision for code tokens, file paths, and exact numbers. Relying solely on keyword search fails when queries use paraphrased or conceptual terminology.

## Decision Drivers
* **Zero External Services:** No standalone server processes (e.g., Qdrant, Milvus, Chroma server, Elasticsearch).
* **Crash Resilience & Low Latency:** ACID transactions, instant reads, durability on power loss.
* **Hybrid Search Recall:** Combination of exact keyword matching and semantic vector similarity.
* **Portability:** Data stored in standard, inspectable, single-file format.

## Considered Options

### Option 1: Specialized Vector DB (DuckDB / LanceDB / Embedded Chroma)
* **Pros:** Specialized for column vectors and columnar analytics.
* **Cons:** Weaker full-text tokenization and transaction ergonomics; higher dependency weight.

### Option 2: Pure Key-Value Store (BadgerDB / RocksDB) + In-memory Vector Index
* **Pros:** Extremely fast raw key-value writes.
* **Cons:** Requires implementing custom B-tree indexing, secondary indexes, and text tokenization from scratch.

### Option 3: SQLite with WAL Mode + FTS5 + `sqlite-vec`
* **Pros:**
  * Single file storage (`battery.db`) readable by any tool in the world.
  * WAL mode (`PRAGMA journal_mode=WAL`) enables concurrent readers without blocking writes.
  * Native **FTS5** table provides BM25 full-text scoring with Porter stemming.
  * **`sqlite-vec`** extension provides native vector similarity search directly inside SQL queries without external vector engines.
  * Merkle SHA-256 deduplication and relationship triples fit naturally in standard relational tables.
* **Cons:** `sqlite-vec` is a dynamic C extension, requiring packaging considerations.

## Decision
We select **Option 3: SQLite (WAL Mode) with FTS5 and `sqlite-vec`**.

### Architecture Invariants:
1. **Concurrency Configuration:**
   ```sql
   PRAGMA journal_mode = WAL;
   PRAGMA synchronous = NORMAL;
   PRAGMA busy_timeout = 5000;
   PRAGMA foreign_keys = ON;
   ```
2. **Hybrid Scoring via Reciprocal Rank Fusion (RRF):**
   Final search scores are computed using rank reciprocal fusion:
   $$\text{RRF\_Score}(d) = \frac{w_{\text{text}}}{k + \text{rank}_{\text{bm25}}(d)} + \frac{w_{\text{vec}}}{k + \text{rank}_{\text{vec}}(d)}$$
   where $k = 5$ (empirically tuned — see `src/battery/evals/rrf_tuning_report.md`),
   $w_{\text{text}} = 0.5$, and $w_{\text{vec}} = 0.5$.
   > **Note:** The academic default $k=60$ is optimised for long-document TREC/MS-MARCO retrieval.
   > For Battery's short factual assertions (1–3 sentences), $k=5$ was found optimal via a
   > grid sweep across 30 parameter combinations on 92 real-world engineering memories,
   > achieving MRR=0.8583 vs MRR=0.8550 at $k=60$.
3. **Deduplication:** Content is SHA-256 content-addressed to prevent redundant duplicate memories across multiple LLM turns.

## Consequences

### Positive
* Single file database with zero network dependencies or external daemons.
* High recall on both technical code symbols and fuzzy semantic concepts.
* Seamless migration and backup via standard SQLite tools (`sqlite3 .dump` or file copy).

### Negative
* Requires loading the `sqlite-vec` extension on engine startup. (Handled via automated fallback or bundled binary).
