import pytest

from battery.config import NEAR_DUP_THRESHOLD
from battery.db import get_connection, init_db, insert_memory, list_memories
from battery.dedup import find_near_duplicate
from battery.embeddings import embed_text


@pytest.fixture
def test_db(tmp_path):
    db_path = tmp_path / "dedup.db"
    conn = get_connection(db_path)
    init_db(conn)
    yield conn
    conn.close()


def test_near_duplicate_merges_same_category(test_db):
    text_a = "All Python functions must include type annotations"
    text_b = "Python functions must include type annotations and docstrings"
    vec_a = embed_text(text_a)
    vec_b = embed_text(text_b)

    first = insert_memory(test_db, text_a, vec_a, category="rule")
    assert first["status"] == "created"

    second = insert_memory(test_db, text_b, vec_b, category="rule")
    assert second["status"] == "merged"
    assert second["similarTo"] == first["id"]
    assert second["similarity"] >= NEAR_DUP_THRESHOLD
    assert len(list_memories(test_db)) == 1
    assert list_memories(test_db)[0]["content"] == text_b


def test_near_duplicate_skips_different_category(test_db):
    text_a = "Use SQLite WAL mode for local storage"
    text_b = "Store data locally with SQLite write-ahead logging"
    vec_a = embed_text(text_a)
    vec_b = embed_text(text_b)

    first = insert_memory(test_db, text_a, vec_a, category="decision")
    second = insert_memory(test_db, text_b, vec_b, category="episodic")

    assert first["status"] == "created"
    assert second["status"] == "created"
    assert len(list_memories(test_db)) == 2


def test_exact_dedup_runs_before_near_duplicate(test_db):
    text = "Never commit secrets to git"
    vec = embed_text(text)

    first = insert_memory(test_db, text, vec, category="rule")
    second = insert_memory(test_db, f"  {text}  ", vec, category="rule")

    assert first["status"] == "created"
    assert second["status"] == "existing"
    assert "similarTo" not in second
    assert len(list_memories(test_db)) == 1


def test_near_dedup_can_be_disabled(test_db):
    text_a = "Prefer hybrid BM25 and vector retrieval"
    text_b = "Use BM25 plus dense vector search together"
    vec_a = embed_text(text_a)
    vec_b = embed_text(text_b)

    insert_memory(test_db, text_a, vec_a, category="decision")
    second = insert_memory(
        test_db,
        text_b,
        vec_b,
        category="decision",
        near_dedup=False,
    )

    assert second["status"] == "created"
    assert len(list_memories(test_db)) == 2


def test_find_near_duplicate_returns_best_match(test_db):
    anchor = "All Python functions must include type annotations"
    vec_anchor = embed_text(anchor)
    insert_memory(test_db, anchor, vec_anchor, category="rule")

    query_vec = embed_text("Python functions must include type annotations and docstrings")
    match = find_near_duplicate(test_db, query_vec, category="rule")
    assert match is not None
    assert match["similarity"] >= NEAR_DUP_THRESHOLD


def test_episodic_memories_are_not_near_deduped(test_db):
    text_a = "Task: First session\nNext step: Continue"
    text_b = "Task: Second session\nNext step: Continue"
    vec_a = embed_text(text_a)
    vec_b = embed_text(text_b)

    first = insert_memory(test_db, text_a, vec_a, category="episodic", source="hook")
    second = insert_memory(test_db, text_b, vec_b, category="episodic", source="hook")

    assert first["status"] == "created"
    assert second["status"] == "created"
    assert len(list_memories(test_db, category="episodic")) == 2


def test_unrelated_memories_are_not_merged(test_db):
    vec_a = embed_text("Use pytest for all Python unit tests")
    vec_b = embed_text("Deploy the frontend to Cloudflare Pages")

    insert_memory(test_db, "Use pytest for all Python unit tests", vec_a, category="rule")
    second = insert_memory(
        test_db,
        "Deploy the frontend to Cloudflare Pages",
        vec_b,
        category="rule",
    )

    assert second["status"] == "created"
    assert len(list_memories(test_db)) == 2
