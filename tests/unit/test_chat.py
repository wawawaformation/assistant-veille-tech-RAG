from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas import ChatRequest


def _make_chunk(article_id: str, score: float = 0.9) -> dict:
    return {
        "id": f"{article_id}:chunk:0",
        "content": f"content of {article_id}",
        "metadata": {"article_id": article_id, "tags": "ai"},
        "score": score,
        "distance": 0.1,
    }


@pytest.fixture
def req() -> ChatRequest:
    return ChatRequest(question="Quoi de neuf en IA ?", topics=["ai"])


@patch("app.chat.compose_answer", new_callable=AsyncMock)
@patch("app.chat.fresh_news.fetch", new_callable=AsyncMock)
@patch("app.chat.ingest_enrich.enrich_retrieval")
@patch("app.chat.retrieval.retrieve")
async def test_handle_chat_full_pipeline(
    mock_retrieve, mock_enrich, mock_fresh, mock_compose, req
) -> None:
    from app.chat import handle_chat

    mock_retrieve.return_value = [_make_chunk("art1"), _make_chunk("art2")]
    mock_enrich.return_value = [_make_chunk("art3")]
    mock_fresh.return_value = [{"title": "Fresh AI news", "url": "http://example.com", "source": "hn"}]
    mock_compose.return_value = MagicMock()

    await handle_chat(req)

    # retrieve reçoit bien les topics
    mock_retrieve.assert_called_once_with("Quoi de neuf en IA ? | ai", k=8, topics=["ai"])

    # enrich est appelé avec le résultat de retrieve
    mock_enrich.assert_called_once()

    # fresh news est appelé
    mock_fresh.assert_called_once_with(topics=["ai"], since=None)

    # compose_answer reçoit retrieved_chunks et fresh_articles
    call_kwargs = mock_compose.call_args.kwargs
    assert "retrieved_chunks" in call_kwargs
    assert "fresh_articles" in call_kwargs
    assert len(call_kwargs["fresh_articles"]) == 1


@patch("app.chat.compose_answer", new_callable=AsyncMock)
@patch("app.chat.fresh_news.fetch", new_callable=AsyncMock)
@patch("app.chat.ingest_enrich.enrich_retrieval")
@patch("app.chat.retrieval.retrieve")
async def test_handle_chat_dedupes_by_article(
    mock_retrieve, mock_enrich, mock_fresh, mock_compose, req
) -> None:
    from app.chat import handle_chat

    # retrieve et enrich renvoient le même article_id
    mock_retrieve.return_value = [_make_chunk("art1"), _make_chunk("art2")]
    mock_enrich.return_value = [_make_chunk("art1")]  # doublon
    mock_fresh.return_value = []
    mock_compose.return_value = MagicMock()

    await handle_chat(req)

    call_kwargs = mock_compose.call_args.kwargs
    # art1 ne doit apparaître qu'une fois
    article_ids = [
        c["metadata"]["article_id"] for c in call_kwargs["retrieved_chunks"]
    ]
    assert article_ids.count("art1") == 1


@patch("app.chat.compose_answer", new_callable=AsyncMock)
@patch("app.chat.fresh_news.fetch", new_callable=AsyncMock)
@patch("app.chat.ingest_enrich.enrich_retrieval", side_effect=NotImplementedError)
@patch("app.chat.retrieval.retrieve")
async def test_handle_chat_survives_enrich_not_implemented(
    mock_retrieve, mock_enrich, mock_fresh, mock_compose, req
) -> None:
    from app.chat import handle_chat

    mock_retrieve.return_value = [_make_chunk("art1")]
    mock_fresh.return_value = []
    mock_compose.return_value = MagicMock()

    await handle_chat(req)  # ne doit pas lever d'exception

    mock_compose.assert_called_once()
