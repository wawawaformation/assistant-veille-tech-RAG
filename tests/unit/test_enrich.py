from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.ingest.enrich import _tags_from_retrieved, enrich_retrieval


# ── _tags_from_retrieved ─────────────────────────────────────────────────────

def test_tags_from_retrieved_extracts_csv_tags() -> None:
    chunks = [
        {"id": "a:0", "metadata": {"tags": "ai,devops"}},
        {"id": "b:0", "metadata": {"tags": "ai,web"}},
    ]
    tags = _tags_from_retrieved(chunks)
    assert set(tags) == {"ai", "devops", "web"}


def test_tags_from_retrieved_ignores_empty_tags() -> None:
    chunks = [{"id": "a:0", "metadata": {"tags": ""}}]
    assert _tags_from_retrieved(chunks) == []


def test_tags_from_retrieved_handles_missing_metadata() -> None:
    chunks = [{"id": "a:0"}]
    assert _tags_from_retrieved(chunks) == []


# ── enrich_retrieval ─────────────────────────────────────────────────────────

def _make_retrieved(ids_tags: list[tuple[str, str]]) -> list[dict]:
    return [
        {"id": chunk_id, "content": "text", "metadata": {"tags": tags, "article_id": chunk_id.split(":")[0]}}
        for chunk_id, tags in ids_tags
    ]


@patch("app.ingest.enrich.get_collection")
def test_enrich_retrieval_returns_new_chunks(mock_get_col) -> None:
    mock_col = MagicMock()
    mock_col.get.return_value = {
        "ids": ["new:chunk:0"],
        "documents": ["new content"],
        "metadatas": [{"tags": "ai", "article_id": "new"}],
    }
    mock_get_col.return_value = mock_col

    retrieved = _make_retrieved([("art1:chunk:0", "ai")])
    result = enrich_retrieval(retrieved)

    assert len(result) == 1
    assert result[0]["id"] == "new:chunk:0"


@patch("app.ingest.enrich.get_collection")
def test_enrich_retrieval_excludes_already_seen_ids(mock_get_col) -> None:
    mock_col = MagicMock()
    # Chroma renvoie un chunk déjà dans retrieved
    mock_col.get.return_value = {
        "ids": ["art1:chunk:0"],
        "documents": ["content"],
        "metadatas": [{"tags": "ai"}],
    }
    mock_get_col.return_value = mock_col

    retrieved = _make_retrieved([("art1:chunk:0", "ai")])
    result = enrich_retrieval(retrieved)

    assert result == []


@patch("app.ingest.enrich.get_collection")
def test_enrich_retrieval_returns_empty_when_no_tags(mock_get_col) -> None:
    retrieved = [{"id": "x:0", "content": "text", "metadata": {"tags": ""}}]
    result = enrich_retrieval(retrieved)

    mock_get_col.assert_not_called()
    assert result == []


@patch("app.ingest.enrich.get_collection", side_effect=Exception("chroma down"))
def test_enrich_retrieval_returns_empty_on_error(mock_get_col) -> None:
    retrieved = _make_retrieved([("art1:chunk:0", "ai")])
    result = enrich_retrieval(retrieved)
    assert result == []
