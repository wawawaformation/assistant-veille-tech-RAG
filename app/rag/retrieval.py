from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.rag.embedding import embed
from app.logger import AppLogger
from app.rag.chroma_client import get_collection

logger = AppLogger.get_logger(__name__)


def _parse_date_or_none(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _freshness_score(metadata: dict[str, Any]) -> float:
    parsed = _parse_date_or_none(metadata.get("date"))
    if parsed is None:
        return 0.0

    now = datetime.now(timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    age_days = (now - parsed.astimezone(timezone.utc)).total_seconds() / 86400.0
    if age_days <= 0:
        return 1.0

    # Decroissance douce: 1.0 a J0, ~0.5 a J7, ~0.2 a J30.
    return 1.0 / (1.0 + (age_days / 7.0))


def _rerank(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for chunk in chunks:
        dist = chunk.get("distance")
        try:
            dist_value = max(float(dist), 0.0) if dist is not None else 1.0
        except (TypeError, ValueError):
            dist_value = 1.0

        # Distance Chroma (cosine) faible = meilleur. On convertit en similarite [0,1].
        semantic_score = 1.0 / (1.0 + dist_value)
        freshness = _freshness_score(chunk.get("metadata") or {})
        chunk["score"] = 0.85 * semantic_score + 0.15 * freshness

    return sorted(chunks, key=lambda c: float(c.get("score", 0.0)), reverse=True)


def _build_where_filter(topics: list[str]) -> dict[str, Any] | None:
    """Construit un filtre ChromaDB sur le champ `tags` (CSV) pour les topics donnés."""
    clean = [t.strip().lower() for t in topics if t.strip()]
    if not clean:
        return None
    if len(clean) == 1:
        return {"tags": {"$contains": clean[0]}}
    return {"$or": [{"tags": {"$contains": t}} for t in clean]}


def retrieve(query: str, k: int = 8, topics: list[str] | None = None) -> list[dict[str, Any]]:
    where = _build_where_filter(topics or [])
    try:
        collection = get_collection()
        query_vec = embed(query)
        kwargs: dict[str, Any] = {"query_embeddings": [query_vec], "n_results": k}
        if where:
            kwargs["where"] = where
        result = collection.query(**kwargs)
    except Exception as exc:
        logger.warning("retrieval failed: %s", exc)
        return []

    docs = (result.get("documents") or [[]])[0]
    metas = (result.get("metadatas") or [[]])[0]
    ids = (result.get("ids") or [[]])[0]
    distances = (result.get("distances") or [[]])[0]

    chunks: list[dict[str, Any]] = []
    for doc_id, doc, meta, dist in zip(ids, docs, metas, distances, strict=False):
        chunks.append(
            {
                "id": doc_id,
                "content": doc,
                "metadata": meta or {},
                "distance": dist,
            }
        )
    return _rerank(chunks)[:k]
