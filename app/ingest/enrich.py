from __future__ import annotations

from typing import Any

from chromadb.api.types import IncludeEnum

from app.logger import AppLogger
from app.rag.chroma_client import get_collection

logger = AppLogger.get_logger(__name__)

_ENRICH_LIMIT = 10


def _tags_from_retrieved(retrieved: list[dict[str, Any]]) -> list[str]:
    """Extrait les tags uniques depuis les métadonnées des chunks récupérés."""
    tags: set[str] = set()
    for chunk in retrieved:
        meta = chunk.get("metadata") or {}
        for tag in str(meta.get("tags", "")).split(","):
            tag = tag.strip().lower()
            if tag:
                tags.add(tag)
    return list(tags)


def _build_where_filter(tags: list[str]) -> dict[str, Any] | None:
    if not tags:
        return None
    if len(tags) == 1:
        return {"tags": {"$contains": tags[0]}}
    return {"$or": [{"tags": {"$contains": t}} for t in tags]}


def enrich_retrieval(retrieved: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Enrichit le résultat de retrieval avec des chunks Chroma filtrés par topics.

    Stratégie : extraire les tags des chunks déjà récupérés, puis interroger
    Chroma via `collection.get()` (filtre metadata seul, pas de vecteur) pour
    ramener des articles thématiquement liés qui auraient été manqués par la
    recherche sémantique pure.
    """
    tags = _tags_from_retrieved(retrieved)
    where = _build_where_filter(tags)
    if not where:
        return []

    seen_ids: set[str] = {str(c.get("id", "")) for c in retrieved}

    try:
        collection = get_collection()
        result = collection.get(
            where=where,
            limit=_ENRICH_LIMIT,
            include=[IncludeEnum.documents, IncludeEnum.metadatas],
        )
    except Exception as exc:
        logger.warning("enrich_retrieval failed: %s", exc)
        return []

    ids = result.get("ids") or []
    docs = result.get("documents") or []
    metas = result.get("metadatas") or []

    enriched: list[dict[str, Any]] = []
    for doc_id, doc, meta in zip(ids, docs, metas):
        if doc_id in seen_ids:
            continue
        enriched.append(
            {
                "id": doc_id,
                "content": doc,
                "metadata": meta or {},
                "distance": None,  # pas de score sémantique pour ces chunks
                "score": 0.0,
            }
        )

    return enriched
