# Battery Context Engine — Living Memory Mirror

> **Notice:** This file mirrors the active state of your local sovereign memory database (`battery.db`).
> It is git-committable and human-editable. Edits and additions will synchronize back to the engine.

## Active Rules & Constraints

- **[ID:2]** All Python code must include strict type annotations and PEP 257 docstrings

## Architectural Decisions

- **[ID:4]** Run all embeddings locally via ONNX all-MiniLM-L6-v2 (384-dim, sub-15ms CPU inference) with zero cloud dependencies
- **[ID:3]** Use SQLite in WAL mode with sqlite-vec and FTS5 fused via Reciprocal Rank Fusion (k=60)
- **[ID:1]** Battery Context Engine operates as an active MCP server on Stdio

## User Preferences & Habits

- **[ID:5]** Prefer functional, immutable data patterns and explicit error handling
