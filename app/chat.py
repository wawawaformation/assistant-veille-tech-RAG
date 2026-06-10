from __future__ import annotations

from app.ingest import enrich as ingest_enrich
from app.logger import AppLogger
from app.rag import retrieval
from app.rag.llm import compose_answer
from app.runtime import fresh_news
from app.schemas import ChatRequest, ChatResponse

logger = AppLogger.get_logger(__name__)


async def handle_chat(req: ChatRequest) -> ChatResponse:
    query = _expand_query(req.question, req.topics)

    retrieved = retrieval.retrieve(query, k=8)

    try:
        enriched = ingest_enrich.enrich_retrieval(retrieved)
    except NotImplementedError:
        enriched = []
    if enriched:
        retrieved = retrieved + enriched

    retrieved = _dedupe_retrieved_by_article(retrieved, limit=8)

    try:
        fresh = await fresh_news.fetch(topics=req.topics, since=None)
    except NotImplementedError:
        fresh = []

    return await compose_answer(
        question=req.question,
        topics=req.topics,
        retrieved_chunks=retrieved,
        fresh_articles=fresh,
    )


def _expand_query(question: str, topics: list[str]) -> str:
    if not topics:
        return question
    return f"{question} | {', '.join(topics)}"


def _dedupe_retrieved_by_article(
    retrieved: list[dict[str, object]],
    limit: int = 8,
) -> list[dict[str, object]]:
    seen: set[str] = set()
    out: list[dict[str, object]] = []

    for chunk in retrieved:
        metadata = chunk.get("metadata")
        meta = metadata if isinstance(metadata, dict) else {}
        article_id = str(meta.get("article_id") or chunk.get("id") or "").strip()

        if not article_id or article_id in seen:
            continue

        seen.add(article_id)
        out.append(chunk)

        if len(out) >= limit:
            break

    return out
