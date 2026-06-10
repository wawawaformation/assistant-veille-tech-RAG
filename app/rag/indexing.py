from __future__ import annotations

import re
from typing import Any, cast

from chromadb.api.types import Embeddings, Metadata

from app.ingest.cleaning import chunk, clean_html_to_markdown, dedupe
from app.rag.chroma_client import get_collection
from app.rag.embedding import embed_many


_HTML_LIKE_RE = re.compile(r"</?[a-zA-Z][^>]*>")


def _normalize_content_for_indexing(content: str) -> str:
    normalized = content.strip()
    if not normalized:
        return ""

    # Si du HTML a traverse l'ingestion, on le reconvertit proprement en markdown.
    if _HTML_LIKE_RE.search(normalized):
        return clean_html_to_markdown(normalized).strip()

    return normalized


def _prepare_chunks(articles: list[dict[str, Any]]) -> tuple[list[str], list[str], list[Metadata]]:
    ids: list[str] = []
    documents: list[str] = []
    metadatas: list[Metadata] = []

    for article in dedupe(articles):
        article_id = str(article.get("id", "")).strip()
        content = _normalize_content_for_indexing(str(article.get("content", "")))

        if not article_id or not content:
            continue

        chunks = chunk(content, max_chars=1200, overlap_chars=200)
        if not chunks:
            continue

        tags = article.get("tags", [])
        if not isinstance(tags, list):
            tags = []

        for chunk_index, chunk_text in enumerate(chunks):
            chunk_id = f"{article_id}:chunk:{chunk_index}"
            ids.append(chunk_id)
            documents.append(chunk_text)
            metadatas.append(
                {
                    "article_id": article_id,
                    "chunk_id": chunk_id,
                    "chunk_index": chunk_index,
                    "chunk_count": len(chunks),
                    "title": str(article.get("title", "")),
                    "source": str(article.get("source", "")),
                    "date": str(article.get("date", "")),
                    "url": str(article.get("url", "")),
                    "tags": ",".join(str(tag) for tag in tags),
                }
            )

    return ids, documents, metadatas


def upsert_articles(articles: list[dict[str, Any]]) -> int:
    """Chunk, embed and upsert normalized articles into Chroma."""

    if not articles:
        return 0

    ids, documents, metadatas = _prepare_chunks(articles)
    if not ids:
        return 0

    try:
        embeddings = cast(Embeddings, embed_many(documents))
        collection = get_collection()
        collection.upsert(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
            embeddings=embeddings,
        )
        return len(ids)
    except Exception as exc:
        print(f"Chroma upsert failed: {exc}")
        return 0
