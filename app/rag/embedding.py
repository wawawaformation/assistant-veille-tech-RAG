from __future__ import annotations

from functools import lru_cache

from sentence_transformers import SentenceTransformer

from app.config import get_settings


@lru_cache(maxsize=1)
def get_embedder() -> SentenceTransformer:
    settings = get_settings()
    return SentenceTransformer(settings.embedding_model)


def embed_many(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []

    embedder = get_embedder()
    vectors = embedder.encode(texts, normalize_embeddings=True)
    return [vector.tolist() for vector in vectors]


def embed(text: str) -> list[float]:
    vectors = embed_many([text])
    return vectors[0] if vectors else []
