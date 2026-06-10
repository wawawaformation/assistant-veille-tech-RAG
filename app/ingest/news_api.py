from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import requests
from bs4 import BeautifulSoup
from pydantic import BaseModel, HttpUrl, ValidationError

from app.config import Settings, get_settings
from app.ingest.cleaning import clean_html_to_markdown, strip_boilerplate
from app.ingest.topics import TOPIC_SYNONYMS
from app.rag.indexing import upsert_articles
from app.schemas import Article


class RawHNItem(BaseModel):
    """Représente un article brut récupéré depuis l'API Hacker News."""

    id: int
    title: str
    url: HttpUrl | None = None
    text: str | None = None
    time: int


@dataclass
class NewsApiIngester:
    """Client d'ingestion Hacker News vers Chroma."""

    settings: Settings | None = None

    def __post_init__(self) -> None:
        """Charge les paramètres de configuration si aucun objet Settings n'est fourni."""

        if self.settings is None:
            self.settings = get_settings()

    def get_last_id(self, number: int) -> list[int]:
        """Retourne les derniers IDs d'articles Hacker News, limités à `number`."""

        settings = self.settings
        if settings is None:
            print("Settings unavailable")
            return []

        if number <= 0:
            return []

        base_url = settings.news_api_base_url.rstrip("/")
        ids_url = f"{base_url}/newstories.json"

        try:
            response = requests.get(ids_url, timeout=10)
            response.raise_for_status()
            story_ids = response.json()
        except requests.RequestException as exc:
            print(f"Failed to fetch newstories: {exc}")
            return []

        if not isinstance(story_ids, list):
            print("Unexpected payload for newstories.json")
            return []

        out: list[int] = []

        for raw_id in story_ids:
            if len(out) >= number:
                break

            try:
                out.append(int(raw_id))
            except (TypeError, ValueError):
                continue

        return out

    def get_story_ids_page(self, page: int = 1, page_size: int = 20) -> list[int]:
        """Retourne une plage d'IDs d'articles Hacker News."""

        if page < 1 or page_size <= 0:
            return []

        needed = page * page_size
        all_ids = self.get_last_id(needed)

        start = (page - 1) * page_size
        end = start + page_size

        return all_ids[start:end]

    def get_item_details(self, item_id: int) -> RawHNItem | None:
        """Récupère les détails d'un article Hacker News à partir de son ID."""

        settings = self.settings
        if settings is None:
            print("Settings unavailable")
            return None

        base_url = settings.news_api_base_url.rstrip("/")
        item_url = f"{base_url}/item/{item_id}.json"

        try:
            response = requests.get(item_url, timeout=10)
            response.raise_for_status()

            item_data = response.json()

            return RawHNItem.model_validate(item_data)

        except (requests.RequestException, ValidationError) as exc:
            print(f"Failed to fetch or parse item {item_id}: {exc}")
            return None

    def _fetch_external_content(self, url: str) -> str | None:
        """Récupère le texte principal de la page externe référencée par Hacker News."""

        min_content_len = 120

        headers = {
            "User-Agent": "nauda-palisse-veille/0.1"
        }

        try:
            response = requests.get(url, timeout=(5, 15), headers=headers)
            response.raise_for_status()
        except requests.RequestException as exc:
            print(f"Failed to fetch external content {url}: {exc}")
            return None

        content_type = response.headers.get("content-type", "").lower()
        html_hint = response.text[:512].lower()
        looks_like_html = "<html" in html_hint or "<!doctype html" in html_hint

        if "text/html" not in content_type and not looks_like_html:
            return None

        soup = BeautifulSoup(response.text, "lxml")
        cleaned_soup = strip_boilerplate(soup)
        normalized_md = clean_html_to_markdown(str(cleaned_soup))

        if len(normalized_md) < min_content_len:
            return None

        return normalized_md

    def _topic_keywords(self, topic: str) -> list[str]:
        """Retourne les mots-clés associés à un topic, synonymes inclus."""

        normalized = topic.lower().strip()

        return [
            normalized,
            *TOPIC_SYNONYMS.get(normalized, []),
        ]

    def _contains_keyword(self, haystack: str, keyword: str) -> bool:
        """
        Vérifie la présence d'un mot-clé dans un texte.

        On utilise une regex avec limites de mots pour éviter que 'ai'
        matche par erreur 'said', 'main', 'email', etc.
        """

        normalized_haystack = haystack.lower()
        normalized_keyword = keyword.lower().strip()

        if not normalized_keyword:
            return False

        pattern = r"\b" + re.escape(normalized_keyword) + r"\b"

        return re.search(pattern, normalized_haystack) is not None

    def _extract_matching_topics(
        self,
        item: RawHNItem,
        topics: list[str],
        external_content: str = "",
    ) -> list[str]:
        """Extrait la liste des topics correspondant à un article donné."""

        if not topics:
            return []

        haystack = " ".join(
            [
                item.title,
                item.text or "",
                str(item.url) if item.url else "",
                external_content,
            ]
        )

        matched: list[str] = []

        for topic in topics:
            keywords = self._topic_keywords(topic)

            if any(self._contains_keyword(haystack, keyword) for keyword in keywords):
                matched.append(topic)

        return matched

    def _to_article(
        self,
        item: RawHNItem,
        matched_topics: list[str],
        external_content: str,
    ) -> Article:
        """Convertit et valide un RawHNItem vers le schéma Article."""

        return Article(
            id=f"hackernews:{item.id}",
            title=item.title,
            source="hackernews",
            date=datetime.fromtimestamp(item.time, tz=timezone.utc),
            content=external_content,
            url=str(item.url) if item.url else f"https://news.ycombinator.com/item?id={item.id}",
            tags=matched_topics,
        )

    def _to_article_dict(self, article: Article) -> dict[str, Any]:
        """Sérialise un Article validé en dictionnaire JSON-compatible."""

        return article.model_dump(mode="json")

    def _collect_matching_articles(
        self,
        story_ids: list[int],
        topics: list[str],
    ) -> list[dict[str, Any]]:
        """Collecte les articles externes correspondant aux topics donnés."""

        articles: list[dict[str, Any]] = []

        for story_id in story_ids:
            item = self.get_item_details(story_id)

            if item is None:
                continue

            if item.url is None:
                # Pour ce POC, on garde seulement les stories qui pointent vers un article externe.
                continue

            external_content = self._fetch_external_content(str(item.url))

            if not external_content:
                continue

            matched_topics = self._extract_matching_topics(
                item=item,
                topics=topics,
                external_content=external_content,
            )

            if topics and not matched_topics:
                continue

            article = self._to_article(
                item=item,
                matched_topics=matched_topics,
                external_content=external_content,
            )

            articles.append(self._to_article_dict(article))

        return articles

    def run(
        self,
        topics: list[str],
        page: int = 1,
        page_size: int = 20,
    ) -> list[dict[str, Any]]:
        """Point d'entrée de l'ingestion : pagination, scraping, normalisation et upsert Chroma."""

        settings = self.settings

        if settings is None:
            print("Settings unavailable")
            return []

        story_ids = self.get_story_ids_page(
            page=page,
            page_size=page_size,
        )

        articles = self._collect_matching_articles(
            story_ids=story_ids,
            topics=topics,
        )

        upserted = upsert_articles(articles)

        print(
            f"Collected {len(articles)} articles "
            f"(page={page}, page_size={page_size}); "
            f"upserted_chunks={upserted}"
        )

        return articles
    