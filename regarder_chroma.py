from __future__ import annotations

import os
from urllib.parse import urlparse

import chromadb
from chromadb.config import Settings as ChromaSettings
from chromadb.api.types import IncludeEnum

from app.config import get_settings


def _resolve_chroma_url() -> str:
    # When running from host, docker service name "chromadb" is not resolvable.
    configured = os.getenv("CHROMA_URL") or get_settings().chroma_url
    parsed = urlparse(configured)
    host = parsed.hostname or "localhost"
    port = parsed.port or 8000

    if host == "chromadb":
        return "http://localhost:8002"
    return f"http://{host}:{port}"


def main() -> int:
    chroma_url = _resolve_chroma_url()
    parsed = urlparse(chroma_url)
    host = parsed.hostname or "localhost"
    port = parsed.port or 8000

    try:
        client = chromadb.HttpClient(
            host=host,
            port=port,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        collection = client.get_or_create_collection(name=get_settings().chroma_collection)
    except Exception as exc:
        print(f"Unable to connect to Chroma at {chroma_url}: {exc}")
        print("Tip: run `make up` and ensure container chromadb is healthy.")
        return 1

    try:
        total = collection.count()
        print(f"Collection: {collection.name}")
        print(f"Total documents: {total}")

        data = collection.get(
            limit=5,
            include=[IncludeEnum.documents, IncludeEnum.metadatas],
        )
        ids = data.get("ids") or []
        docs = data.get("documents") or []
        metas = data.get("metadatas") or []

        if not ids:
            print("No documents found.")
            return 0

        for i, doc_id in enumerate(ids):
            print(f"\n[{i + 1}] id={doc_id}")
            print(docs[i] if i < len(docs) else "")
            print(metas[i] if i < len(metas) else {})
        return 0
    except Exception as exc:
        print(f"Failed to read collection data: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())