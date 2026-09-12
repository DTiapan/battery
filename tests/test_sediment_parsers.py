from battery.evals.sediment.memex_adapter import _parse_memex_recall


def test_parse_memex_recall_json():
    text = '{"results": [{"id": "abc", "content": "Use SQLite WAL mode"}]}'
    items = _parse_memex_recall(text)
    assert len(items) == 1
    assert items[0]["content"] == "Use SQLite WAL mode"


def test_parse_memex_recall_text_blocks():
    text = "1. [id=mem-1] Prefer explicit LIMIT clauses on SQL\n2. [id=mem-2] Use hybrid search"
    items = _parse_memex_recall(text)
    assert len(items) == 2
    assert "LIMIT" in items[0]["content"]
