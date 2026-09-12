from battery.db import get_connection, hash_file_snippet, init_db, insert_memory
from battery.retrieval import hybrid_search
from battery.verify import filter_verified_results, verify_citation, verify_memory


def test_verify_citation_missing_file(tmp_path):
    citation = {"file_path": str(tmp_path / "gone.py"), "snippet_hash": "abc"}
    assert verify_citation(citation) == "missing"


def test_verify_citation_stale_on_change(tmp_path):
    file_path = tmp_path / "api.py"
    file_path.write_text("def old_api(): pass\n", encoding="utf-8")
    snippet_hash = hash_file_snippet(file_path)
    citation = {"file_path": str(file_path), "snippet_hash": snippet_hash}

    assert verify_citation(citation) == "valid"

    file_path.write_text("def new_api(): pass\n", encoding="utf-8")
    assert verify_citation(citation) == "stale"


def test_recall_excludes_stale_memory(tmp_path):
    db_path = tmp_path / "verify.db"
    conn = get_connection(db_path)
    init_db(conn)

    file_path = tmp_path / "config.py"
    file_path.write_text("PORT = 5432\n", encoding="utf-8")
    fake_vec = [0.3] * 384

    result = insert_memory(
        conn,
        "Database listens on port 5432",
        fake_vec,
        category="decision",
        citations=[{"file_path": str(file_path), "snippet_hash": hash_file_snippet(file_path)}],
    )
    conn.commit()

    matches = hybrid_search(conn, "port 5432", limit=5)
    assert len(matches) == 1

    file_path.write_text("PORT = 3306\n", encoding="utf-8")
    status = verify_memory(conn, result["id"])
    assert status == "stale"

    filtered = filter_verified_results(conn, matches)
    assert filtered == []
