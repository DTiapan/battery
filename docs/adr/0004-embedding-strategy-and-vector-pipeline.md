# ADR 0004: Embedding Strategy and Local Vector Pipeline

## Status
Accepted

## Date
2026-09-11

## Context
The Battery Context Engine requires dense vector representations to power semantic retrieval alongside SQLite FTS5 keyword search. 

Relying on external cloud embedding APIs (e.g., OpenAI, Cohere) introduces significant latency (100–300ms network roundtrips), cost, API key management friction, and fundamentally violates the engine's core philosophical constraint: **local sovereignty and zero network dependencies**.

Conversely, bundling heavy deep-learning frameworks (like PyTorch or full HuggingFace Transformers) introduces multi-gigabyte dependencies and multi-second startup delays that conflict with a snappy local agent experience.

## Decision Drivers
* **Local Sovereignty & Privacy:** Embeddings must be generated locally on-device without cloud network calls.
* **Low Latency on Commodity Hardware:** CPU inference latency must remain under 25ms per memory chunk on modern consumer laptops without requiring dedicated GPUs.
* **Minimal Memory Footprint:** The embedding runtime and model weights must fit comfortably under 150MB of RAM.
* **Portability:** Embeddings must use standard 384-dimensional dense vectors compatible with both Python (V1) and Go (V2) through ONNX Runtime or GGUF/C-bindings.

## Considered Options

### Option 1: External Cloud API (e.g., OpenAI `text-embedding-3-small`)
* **Pros:** Zero local CPU load, high semantic quality.
* **Cons:** Network latency, API cost, requires external credentials, breaks offline functionality, violates sovereign privacy premise.

### Option 2: Heavy Local PyTorch / Transformers Pipeline
* **Pros:** Access to any model from Hugging Face hub.
* **Cons:** Massive dependency footprint (>2GB), slow process startup (several seconds), high idle memory usage.

### Option 3: Local Quantized ONNX Runtime (`all-MiniLM-L6-v2` / `bge-small-en-v1.5`) with Ollama Fallback
* **Pros:**
  * Self-contained, zero-configuration engine running directly on CPU via optimized ONNX Runtime (`fastembed`).
  * `all-MiniLM-L6-v2` produces compact 384-dimensional embeddings in ~12ms on CPU.
  * Model weights are ~90MB and cached locally in `~/.battery/models/`.
  * Allows optional transparent delegation to an existing local Ollama instance (`/api/embeddings`) if the user already has one active.
* **Cons:** Fixed 384-dimension limit requires re-indexing if changing to a different dimension model later.

## Decision
We select **Option 3: Local ONNX Runtime with `all-MiniLM-L6-v2` (384-dim)** as the standard default embedding pipeline.

### Vector Pipeline Specifications:
1. **Model & Dimensions:**
   * Model: `all-MiniLM-L6-v2` (384 dimensions, normalized float32 vectors).
   * Metric: Cosine similarity (`distance_metric=cosine` in `sqlite-vec`).
2. **Runtime Engine:**
   * Packaged via `fastembed` (built on `onnxruntime` with native SIMD/AVX2 acceleration).
   * Secondary adapter: Optional Ollama client if configured in `~/.battery/config.json`.
3. **Chunking & Memory Granularity:**
   * **Atomic Rules & Preferences (Working/Semantic Memory):** Stored unchunked as singular standalone assertions (max 256 tokens) to maximize retrieval precision.
   * **Narrative / Documentation Memories (Episodic):** Segmented using markdown-aware paragraph chunking (chunk size: 384 tokens, overlap: 64 tokens).
4. **Vector Storage:**
   * Managed via `sqlite-vec` virtual table (`vec_memories` using `float[384]`).

## Consequences

### Positive
* 100% offline and private; zero external API keys or subscription requirements.
* Fast local inference (~10–15ms) guarantees end-to-end MCP retrieval under 50ms.
* Compact vector footprint: 384 floats = 1,536 bytes per vector (10,000 memories take only ~15MB in SQLite).

### Negative
* First run requires a one-time download of the ~90MB ONNX model weights into `~/.battery/models/`. (Progress displayed gracefully in CLI).
