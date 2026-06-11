from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

import httpx

from app.config import get_settings
from app.ingest.topics import TOPIC_SYNONYMS
from app.logger import AppLogger

logger = AppLogger.get_logger(__name__)

_DEFAULT_LIMIT = 30
_HTTP_TIMEOUT = 8.0


def _topic_keywords(topic: str) -> list[str]:
    """Retourne les mots-clés associés à un topic, synonymes inclus."""
    normalized = topic.lower().strip()
    return [normalized, *TOPIC_SYNONYMS.get(normalized, [])]


def _contains_keyword(haystack: str, keyword: str) -> bool:
    """Vérifie la présence d'un mot-clé dans un texte avec limites de mots."""
    normalized_haystack = haystack.lower()
    normalized_keyword = keyword.lower().strip()
    if not normalized_keyword:
        return False
    pattern = r"\b" + re.escape(normalized_keyword) + r"\b"
    return re.search(pattern, normalized_haystack) is not None


def _extract_matching_topics(title: str, url: str, text: str, topics: list[str]) -> list[str]:
    """Retourne la liste des topics dont au moins un mot-clé apparaît dans le texte de l'article."""
    haystack = f"{title} {url} {text}"
    matched: list[str] = []
    for topic in topics:
        keywords = _topic_keywords(topic)
        if any(_contains_keyword(haystack, kw) for kw in keywords):
            matched.append(topic)
    return matched


async def fetch(
    topics: list[str],
    since: datetime | None = None,
) -> list[dict[str, Any]]:
   

    # 1. Si topics vide → retourner []
    # 2. Appeler l'API HN pour récupérer les derniers IDs
    # 3. Pour chaque ID, récupérer les détails de l'article
    # 4. Filtrer par topics (chercher les mots-clés dans le titre/url)
    # 5. Filtrer par `since` si fourni. Il faudra regler ce probleme de timezone aware qui fait louper le test
     # 6. Retourner des dicts avec : title, url, source, date, content, tags
    
    
    
    if not topics:
        return []

   
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        response = await client.get("https://hacker-news.firebaseio.com/v0/newstories.json")
        response.raise_for_status()
        ids = response.json()

   
    articles: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        for article_id in ids[:_DEFAULT_LIMIT]:
            response = await client.get(f"https://hacker-news.firebaseio.com/v0/item/{article_id}.json")
            response.raise_for_status()
            article = response.json()
            articles.append(article)

    
    filtered_articles = [
        article for article in articles
        if _extract_matching_topics(article.get("title", ""), article.get("url", ""), article.get("text", ""), topics)
    ]

    
    if since:
        filtered_articles = [
            article for article in filtered_articles
            if datetime.fromtimestamp(article.get("time", 0)) > since
        ]

   
    return [
        {
            "title": article.get("title", ""),
            "url": article.get("url", ""),
            "source": "hn",
            "date": datetime.fromtimestamp(article.get("time", 0), tz=timezone.utc).isoformat(),
            "content": article.get("text", ""),
            "tags": _extract_matching_topics(article.get("title", ""), article.get("url", ""), article.get("text", ""), topics),
        }
        for article in filtered_articles
    ]
    