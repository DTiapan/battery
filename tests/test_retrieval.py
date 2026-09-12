import pytest

from battery.db import get_connection, init_db, insert_memory
from battery.embeddings import embed_text
from battery.retrieval import hybrid_search


@pytest.fixture
def populated_db(tmp_path):
    db_path = tmp_path / "test_retrieval.db"
    conn = get_connection(db_path)
    init_db(conn)

    # Insert test dataset covering distinct categories and keyword/semantic concepts
    test_corpus = [
        ("Always use snake_case for Python function and variable names", "rule"),
        ("Architecture decision: use SQLite in WAL mode for local storage substrate", "decision"),
        ("PostgreSQL production database operates on port 5432 with replica on 5433", "general"),
        ("User prefers dark mode themes and high-contrast syntax highlighting", "preference"),
        ("Git commit messages must adhere to conventional commits format", "rule"),
    ]

    for content, category in test_corpus:
        vec = embed_text(content)
        insert_memory(conn, content, vec, category=category)

    yield conn
    conn.close()


def test_exact_keyword_retrieval(populated_db):
    # Query for exact rare token '5432'
    results = hybrid_search(populated_db, "5432", limit=3)
    assert len(results) > 0
    top = results[0]
    assert "5432" in top["content"]
    assert top["bm25_rank"] is not None


def test_semantic_similarity_retrieval(populated_db):
    # Query with semantic paraphrase: "guidelines for writing python code"
    results = hybrid_search(populated_db, "guidelines for writing python code", limit=3)
    assert len(results) > 0
    top = results[0]
    assert "snake_case" in top["content"]


def test_category_filtering(populated_db):
    # Search with category filter
    results = hybrid_search(populated_db, "format", category="rule", limit=5)
    for r in results:
        assert r["category"] == "rule"


def test_adaptive_rrf_weights_small_corpus(populated_db):
    from battery.retrieval import _resolve_rrf_weights
    from battery.config import DEFAULT_TEXT_WEIGHT, DEFAULT_VEC_WEIGHT

    tw, vw = _resolve_rrf_weights(5, DEFAULT_TEXT_WEIGHT, DEFAULT_VEC_WEIGHT)
    assert tw == DEFAULT_TEXT_WEIGHT
    assert vw == DEFAULT_VEC_WEIGHT


def test_adaptive_rrf_weights_large_corpus():
    from battery.retrieval import _resolve_rrf_weights
    from battery.config import (
        DEFAULT_TEXT_WEIGHT,
        DEFAULT_VEC_WEIGHT,
        LARGE_CORPUS_RRF_THRESHOLD,
        LARGE_CORPUS_TEXT_WEIGHT,
        LARGE_CORPUS_VEC_WEIGHT,
    )

    tw, vw = _resolve_rrf_weights(
        LARGE_CORPUS_RRF_THRESHOLD, DEFAULT_TEXT_WEIGHT, DEFAULT_VEC_WEIGHT
    )
    assert tw == LARGE_CORPUS_TEXT_WEIGHT
    assert vw == LARGE_CORPUS_VEC_WEIGHT

    # Explicit overrides are preserved at scale
    tw, vw = _resolve_rrf_weights(LARGE_CORPUS_RRF_THRESHOLD, 0.6, 0.4)
    assert tw == 0.6
    assert vw == 0.4
