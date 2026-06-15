from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.rag.embedding import embed
from app.logger import AppLogger
from app.rag.chroma_client import get_collection
from app.ingest.topics import TOPIC_SYNONYMS

logger = AppLogger.get_logger(__name__)


def _parse_date_or_none(value: Any) -> datetime | None:
    """Convertit une valeur quelconque en datetime aware UTC, ou None si invalide."""
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
    """Calcule un score de fraîcheur entre 0.0 et 1.0 basé sur la date du document.

    Décroissance douce : 1.0 à J0, ~0.5 à J7, ~0.2 à J30.
    Retourne 0.0 si la date est absente ou invalide.
    """
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
    """Recalcule et trie les chunks par score combiné sémantique + fraîcheur.

    Score final = 85 % similarité sémantique + 15 % fraîcheur.
    La distance Chroma (cosine) est convertie en similarité [0, 1] via 1/(1+dist).
    """
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
    """Construit un filtre where_document ChromaDB ($contains) pour les topics."""
    terms: set[str] = set()
    for topic in topics:
        normalized = topic.strip().lower()
        if not normalized:
            continue
        terms.add(normalized)
        for alias in TOPIC_SYNONYMS.get(normalized, []):
            alias_norm = alias.strip().lower()
            if alias_norm:
                terms.add(alias_norm)

    clean = sorted(terms)
    if not clean:
        return None
    if len(clean) == 1:
        return {"$contains": clean[0]} 
    return {"$or": [{"$contains": t} for t in clean]}


def _query_collection(k: int, query_vec: list[float], where: dict[str, Any] | None) -> dict[str, Any]:
    """Interroge la collection ChromaDB avec le vecteur de requête et un filtre optionnel.

    Retourne le dictionnaire brut renvoyé par ChromaDB (ids, documents, metadatas, distances).
    """
    collection = get_collection()
    kwargs: dict[str, Any] = {"query_embeddings": [query_vec], "n_results": k}
    if where:
        kwargs["where_document"] = where
    result = collection.query(**kwargs)
    return dict(result) if result else {}


def retrieve(query: str, k: int = 8, topics: list[str] | None = None) -> list[dict[str, Any]]:
    """Recherche les k chunks les plus pertinents pour une requête textuelle.

    Args:
        query:  Texte de la question posée par l'utilisateur.
        k:      Nombre maximum de chunks à retourner (défaut 8).
        topics: Liste de sujets pour filtrer les documents (ex. ["ai-ml", "python"]).
                Si le filtre ne retourne aucun résultat, la recherche est relancée
                sans filtre pour garantir un contexte minimal.

    Returns:
        Liste de chunks triés par score décroissant, chacun contenant :
        id, content, metadata, distance et score.
    """
    where = _build_where_filter(topics or [])
    try:
        query_vec = embed(query)
        result = _query_collection(k=k, query_vec=query_vec, where=where)

        # Fallback defensif: si le filtre topics est trop restrictif, on retente
        # sans filtre pour garder de la matiere de contexte dans la reponse.
        if where and not ((result.get("ids") or [[]])[0]):
            logger.info("retrieval: no match with where filter, retrying without filter")
            result = _query_collection(k=k, query_vec=query_vec, where=None)
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
