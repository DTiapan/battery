import re
import sqlite3
from typing import Any, Dict, List, Optional
from battery.config import DEFAULT_TEXT_WEIGHT, DEFAULT_VEC_WEIGHT, RRF_K
from battery.db import serialize_vector
from battery.embeddings import embed_text

def sanitize_fts5_query(query: str) -> str:
    """Escapes punctuation and formats alphanumeric tokens for SQLite FTS5."""
    tokens = re.findall(r"\w+", query)
    if not tokens:
        return '""'
    # Match each token as a prefix or quoted word
    return " ".join(f'"{token}"*' for token in tokens)

def hybrid_search(
    conn: sqlite3.Connection,
    query: str,
    limit: int = 5,
    category: Optional[str] = None,
    text_weight: float = DEFAULT_TEXT_WEIGHT,
    vec_weight: float = DEFAULT_VEC_WEIGHT,
    k: int = RRF_K,
) -> List[Dict[str, Any]]:
    """
    Executes hybrid search fusing BM25 (FTS5) and dense vector (sqlite-vec)
    using Reciprocal Rank Fusion (RRF).
    """
    query_clean = query.strip()
    if not query_clean:
        return []

    # 1. BM25 search via FTS5
    bm25_ranks: Dict[int, int] = {}
    fts_query = sanitize_fts5_query(query_clean)
    try:
        cursor = conn.execute(
            """
            SELECT rowid as memory_id
            FROM memories_fts
            WHERE memories_fts MATCH ?
            ORDER BY rank
            LIMIT 50
            """,
            (fts_query,)
        )
        for rank_idx, row in enumerate(cursor.fetchall()):
            bm25_ranks[row["memory_id"]] = rank_idx + 1
    except sqlite3.OperationalError:
        # Gracefully handle any FTS5 syntax edge cases
        pass

    # 2. Vector search via sqlite-vec
    vec_ranks: Dict[int, int] = {}
    query_vec = embed_text(query_clean)
    query_bytes = serialize_vector(query_vec)
    cursor = conn.execute(
        """
        SELECT memory_id, distance
        FROM vec_memories
        WHERE embedding MATCH ? AND k = 50
        ORDER BY distance ASC
        """,
        (query_bytes,)
    )
    for rank_idx, row in enumerate(cursor.fetchall()):
        vec_ranks[row["memory_id"]] = rank_idx + 1

    # 3. Reciprocal Rank Fusion (RRF)
    all_memory_ids = set(bm25_ranks.keys()) | set(vec_ranks.keys())
    if not all_memory_ids:
        return []

    rrf_scores: Dict[int, float] = {}
    for mem_id in all_memory_ids:
        score = 0.0
        if mem_id in bm25_ranks:
            score += text_weight / (k + bm25_ranks[mem_id])
        if mem_id in vec_ranks:
            score += vec_weight / (k + vec_ranks[mem_id])
        rrf_scores[mem_id] = score

    # 4. Fetch memory contents and metadata
    placeholders = ",".join("?" for _ in all_memory_ids)
    sql = f"""
        SELECT id, content, category, importance, created_at, updated_at
        FROM memories
        WHERE id IN ({placeholders}) AND is_deleted = 0
    """
    params: List[Any] = list(all_memory_ids)
    if category:
        sql += " AND category = ?"
        params.append(category)

    cursor = conn.execute(sql, params)
    rows = {row["id"]: dict(row) for row in cursor.fetchall()}

    results = []
    for mem_id, score in rrf_scores.items():
        if mem_id in rows:
            record = rows[mem_id]
            record["score"] = round(score, 6)
            record["bm25_rank"] = bm25_ranks.get(mem_id)
            record["vec_rank"] = vec_ranks.get(mem_id)
            results.append(record)

    # Sort descending by fused RRF score
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:limit]
