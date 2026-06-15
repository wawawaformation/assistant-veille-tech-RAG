from __future__ import annotations

from app.logger import AppLogger
from app.rag import retrieval
from app.rag.llm import compose_answer
from app.runtime import fresh_news
from app.schemas import ChatRequest, ChatResponse

logger = AppLogger.get_logger(__name__)


async def handle_chat(req: ChatRequest) -> ChatResponse:
    """Orchestre le pipeline RAG pour une requête de chat.

    Étapes :
    1. Enrichit la requête avec les topics pour améliorer la recherche sémantique.
    2. Récupère les chunks pertinents depuis le vector store.
    3. Déduplique les chunks pour ne garder qu'un seul par article source.
    4. Récupère les articles récents depuis Hacker News.
    5. Génère et retourne la réponse via le LLM.
    """
    query = _expand_query(req.question, req.topics)

    retrieved = retrieval.retrieve(query, k=8, topics=req.topics)

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
    """Ajoute les topics à la question pour élargir la couverture de la recherche sémantique."""
    if not topics:
        return question
    return f"{question} | {', '.join(topics)}"


def _dedupe_retrieved_by_article(
    retrieved: list[dict[str, object]],
    limit: int = 8,
) -> list[dict[str, object]]:
    """Retourne au maximum `limit` chunks en ne conservant que le premier chunk par article."""
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
