from __future__ import annotations

from functools import lru_cache
from urllib.parse import urlparse

import chromadb
from chromadb.api.models.Collection import Collection
from chromadb.config import Settings as ChromaSettings

from app.config import get_settings


@lru_cache(maxsize=1)
def get_client():
    """Crée et retourne le client HTTP ChromaDB (singleton via lru_cache).

    Lit l'URL de connexion depuis la configuration de l'application et se connecte
    au serveur ChromaDB distant. La télémétrie anonyme est désactivée.
    """
    settings = get_settings()
    parsed = urlparse(settings.chroma_url)
    host = parsed.hostname or "chromadb"
    port = parsed.port or 8000
    return chromadb.HttpClient(
        host=host,
        port=port,
        settings=ChromaSettings(anonymized_telemetry=False),
    )


def get_collection() -> Collection:
    """Retourne la collection ChromaDB de l'application, en la créant si elle n'existe pas.

    Utilise la distance cosine (HNSW) comme espace de similarité vectorielle.
    Le nom de la collection est lu depuis la configuration de l'application.
    """
    settings = get_settings()
    client = get_client()
    return client.get_or_create_collection(
        name=settings.chroma_collection,
        metadata={"hnsw:space": "cosine"},
    )
