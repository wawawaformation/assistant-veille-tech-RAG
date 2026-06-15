from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.rag.retrieval import _build_where_filter, retrieve


# ── _build_where_filter ──────────────────────────────────────────────────────

def test_build_where_filter_empty_returns_none() -> None:
    assert _build_where_filter([]) is None


def test_build_where_filter_single_topic() -> None:
    result = _build_where_filter(["ai"])
    assert result == {"$contains": "ai"}


def test_build_where_filter_multiple_topics() -> None:
    result = _build_where_filter(["ai", "devops"])
    assert result == {
        "$or": [
            {"$contains": "ai"},
            {"$contains": "devops"},
            {"$contains": "docker"},
            {"$contains": "infrastructure"},
            {"$contains": "kubernetes"},
        ]
    }


def test_build_where_filter_strips_and_lowercases() -> None:
    result = _build_where_filter(["  AI  "])
    assert result == {"$contains": "ai"}


def test_build_where_filter_ignores_blank_entries() -> None:
    result = _build_where_filter(["", "  ", "python"])
    assert result == {
        "$or": [
            {"$contains": "programming"},
            {"$contains": "python"},
        ]
    }


def test_build_where_filter_expands_frontend_slug_aliases() -> None:
    result = _build_where_filter(["ai-ml"])
    assert result == {
        "$or": [
            {"$contains": "ai"},
            {"$contains": "ai-ml"},
            {"$contains": "llm"},
            {"$contains": "machine learning"},
        ]
    }


# ── retrieve ─────────────────────────────────────────────────────────────────

def _make_chroma_result(n: int = 2) -> dict:
    ids = [[f"art{i}:chunk:0" for i in range(n)]]
    docs = [[f"content {i}" for i in range(n)]]
    metas = [[{"article_id": f"art{i}", "tags": "ai", "date": "2024-01-01T00:00:00+00:00"} for i in range(n)]]
    distances = [[0.1 * i for i in range(n)]]
    return {"ids": ids, "documents": docs, "metadatas": metas, "distances": distances}


@patch("app.rag.retrieval.get_collection")
@patch("app.rag.retrieval.embed", return_value=[0.1, 0.2, 0.3])
def test_retrieve_returns_chunks(mock_embed, mock_get_col) -> None:
    mock_col = MagicMock()
    mock_col.query.return_value = _make_chroma_result(2)
    mock_get_col.return_value = mock_col

    result = retrieve("test query", k=2)

    assert len(result) == 2
    assert result[0]["content"] == "content 0"
    assert "score" in result[0]


@patch("app.rag.retrieval.get_collection")
@patch("app.rag.retrieval.embed", return_value=[0.1, 0.2, 0.3])
def test_retrieve_passes_where_filter_to_chroma(mock_embed, mock_get_col) -> None:
    mock_col = MagicMock()
    mock_col.query.return_value = _make_chroma_result(1)
    mock_get_col.return_value = mock_col

    retrieve("test query", k=4, topics=["ai"])

    call_kwargs = mock_col.query.call_args.kwargs
    assert call_kwargs["where_document"] == {"$contains": "ai"}
    assert call_kwargs["n_results"] == 4


@patch("app.rag.retrieval.get_collection")
@patch("app.rag.retrieval.embed", return_value=[0.1, 0.2, 0.3])
def test_retrieve_no_topics_no_where_filter(mock_embed, mock_get_col) -> None:
    mock_col = MagicMock()
    mock_col.query.return_value = _make_chroma_result(1)
    mock_get_col.return_value = mock_col

    retrieve("test query", k=4, topics=[])

    call_kwargs = mock_col.query.call_args.kwargs
    assert "where" not in call_kwargs


@patch("app.rag.retrieval.get_collection", side_effect=Exception("chroma down"))
@patch("app.rag.retrieval.embed", return_value=[0.1])
def test_retrieve_returns_empty_on_error(mock_embed, mock_get_col) -> None:
    result = retrieve("query")
    assert result == []


@patch("app.rag.retrieval.get_collection")
@patch("app.rag.retrieval.embed", return_value=[0.1, 0.2, 0.3])
def test_retrieve_retries_without_where_when_filtered_result_empty(mock_embed, mock_get_col) -> None:
    mock_col = MagicMock()
    mock_col.query.side_effect = [
        {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]},
        _make_chroma_result(1),
    ]
    mock_get_col.return_value = mock_col

    result = retrieve("test query", k=4, topics=["ai-ml"])

    assert len(result) == 1
    assert mock_col.query.call_count == 2
    first_call = mock_col.query.call_args_list[0].kwargs
    second_call = mock_col.query.call_args_list[1].kwargs
    assert "where_document" in first_call
    assert "where_document" not in second_call
