from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from langchain_openai import AzureChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

from app.config import get_settings
from app.logger import AppLogger
from app.schemas import ArticleCard, ChatResponse

logger = AppLogger.get_logger(__name__)


SYSTEM_PROMPT = (
    "Tu es l'assistant de veille technologique interne de Nauda Palisse.\n"
    "Réponds en français, factuel, concis. Cite tes sources via les cartes d'articles.\n"
    "Si aucun article n'est fourni, dis-le poliment et ne fabrique rien.\n"
    "Format de sortie attendu : JSON strict avec les clés `answer` (string) "
    "et `cards` (liste d'objets {title, source, date, snippet, url, tags})."
)


@lru_cache(maxsize=1)
def get_llm() -> AzureChatOpenAI | None:
    settings = get_settings()
    if not settings.azure_ai_inference_endpoint or not settings.azure_ai_inference_api_key:
        logger.info("Azure AI inference not configured — running in degraded mode")
        return None
    # L'endpoint Azure AI Foundry se présente sous la forme
    # https://<resource>.services.ai.azure.com/openai/v1 — on passe la base
    # sans le suffixe /openai/v1 car AzureChatOpenAI le reconstruit lui-même.
    base = settings.azure_ai_inference_endpoint.removesuffix("/openai/v1").removesuffix("/")
    return AzureChatOpenAI(
        azure_endpoint=base,
        api_key=settings.azure_ai_inference_api_key,
        azure_deployment=settings.azure_ai_inference_model,
        api_version=settings.azure_ai_inference_api_version,
        temperature=0.2,
    )


def _format_context(retrieved: list[dict[str, Any]], fresh: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    if retrieved:
        parts.append("## Index interne")
        for i, chunk in enumerate(retrieved, 1):
            meta = chunk.get("metadata") or {}
            parts.append(
                f"[{i}] {meta.get('title', '')} — {meta.get('source', '')} "
                f"({meta.get('date', '')})\n{chunk.get('content', '')[:600]}"
            )
    if fresh:
        parts.append("## Actualité fraîche")
        for i, art in enumerate(fresh, 1):
            parts.append(
                f"[F{i}] {art.get('title', '')} — {art.get('source', '')} "
                f"({art.get('date', '')})\n{art.get('content', '')[:600]}\n{art.get('url', '')}"
            )
    return "\n\n".join(parts) if parts else "(aucune source disponible)"


def _build_cards(
    retrieved: list[dict[str, Any]], fresh: list[dict[str, Any]]
) -> list[ArticleCard]:
    cards: list[ArticleCard] = []
    for chunk in retrieved:
        meta = chunk.get("metadata") or {}
        snippet = (chunk.get("content") or "")[:280]
        cards.append(
            ArticleCard(
                title=meta.get("title", "Sans titre"),
                source=meta.get("source", "interne"),
                date=meta.get("date"),
                snippet=snippet,
                url=meta.get("url", ""),
                tags=_split_tags(meta.get("tags")),
            )
        )
    for art in fresh:
        cards.append(
            ArticleCard(
                title=art.get("title", "Sans titre"),
                source=art.get("source", "newsapi"),
                date=art.get("date"),
                snippet=(art.get("content") or art.get("description") or "")[:280],
                url=art.get("url", ""),
                tags=art.get("tags", []),
            )
        )
    return cards


def _split_tags(raw: Any) -> list[str]:
    if not raw:
        return []
    if isinstance(raw, list):
        return [str(x) for x in raw]
    if isinstance(raw, str):
        return [t.strip() for t in raw.split(",") if t.strip()]
    return []


async def compose_answer(
    *,
    question: str,
    topics: list[str],
    retrieved_chunks: list[dict[str, Any]],
    fresh_articles: list[dict[str, Any]],
) -> ChatResponse:
    cards = _build_cards(retrieved_chunks, fresh_articles)

    if not retrieved_chunks and not fresh_articles:
        return ChatResponse(
            answer=(
                "Aucun article ne couvre encore ce sujet dans l'index ou dans "
                "l'actualité collectée. Lance une ingestion pour alimenter la veille."
            ),
            cards=[],
            status="empty",
        )

    llm = get_llm()
    if llm is None:
        return ChatResponse(
            answer=(
                f"{len(cards)} article(s) trouvé(s) pour : {question}. "
                "LLM non configuré — voici les sources brutes."
            ),
            cards=cards,
            status="degraded",
        )

    user_payload = {
        "question": question,
        "topics": topics,
        "context": _format_context(retrieved_chunks, fresh_articles),
    }

    try:
        msg = await llm.ainvoke(
            [
                SystemMessage(content=SYSTEM_PROMPT),
                HumanMessage(content=json.dumps(user_payload, ensure_ascii=False)),
            ]
        )
        raw = msg.content if isinstance(msg.content, str) else str(msg.content)
        answer = _extract_answer(raw)
    except Exception as exc:
        logger.exception("LLM call failed: %s", exc)
        answer = f"Synthèse indisponible (erreur LLM). {len(cards)} article(s) référencé(s)."

    return ChatResponse(answer=answer, cards=cards, status="ok")


def _strip_markdown_fence(raw: str) -> str:
    """Enlève les blocs ```json ... ``` que certains LLM ajoutent."""
    stripped = raw.strip()
    if stripped.startswith("```"):
        stripped = stripped.split("\n", 1)[-1]
        if stripped.endswith("```"):
            stripped = stripped[: stripped.rfind("```")]
    return stripped.strip()


def _extract_answer(raw: str) -> str:
    try:
        data = json.loads(_strip_markdown_fence(raw))
        if isinstance(data, dict) and "answer" in data:
            return str(data["answer"])
    except json.JSONDecodeError:
        pass
    return raw.strip()
