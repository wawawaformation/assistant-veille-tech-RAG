from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import requests

from app.config import Settings, get_settings
from pydantic import BaseModel, HttpUrl, ValidationError
from app.schemas import Article


class RawHNItem(BaseModel):
    """ Représente un article brut récupéré de l'API Hacker News """
    
    id: int
    title: str
    url: HttpUrl | None = None
    text: str | None = None
    time: int


TOPIC_SYNONYMS: dict[str, list[str]] = {
    "technology": ["tech", "software", "digital", "computer", "internet", "ai"],
    "programming": ["code", "coding", "developer", "dev", "python", "javascript", "rust", "java", "golang"],
}
    


@dataclass
class NewsApiIngester:
    settings: Settings | None = None

    def __post_init__(self) -> None:
        """ Charge les paramètres de configuration si pas déjà fournis """
        
        if self.settings is None:
            self.settings = get_settings()
            
            

    def get_last_id(self, number: int) -> list[int]:
        
        """ retourne les derniers IDs d'articles Hacker News, limités à `number` """
        
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
    
    
    def get_item_details(self, item_id: int) -> RawHNItem | None:
        
        """ Récupère les détails d'un article Hacker News à partir de son ID """
        
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

    def _topic_keywords(self, topic: str) -> list[str]:
        
        """ Retourne la liste des mots-clés associés à un topic donné, en incluant les synonymes """
        normalized = topic.lower().strip()
        return [normalized, *TOPIC_SYNONYMS.get(normalized, [])]

    def _extract_matching_topics(self, item: RawHNItem, topics: list[str]) -> list[str]:
        
        """ Extrait la liste des topics correspondants à un article donné """
        if not topics:
            return []
        haystack = " ".join([
            (item.title or ""),
            (item.text or ""),
            str(item.url) if item.url else "",
        ]).lower()

        matched: list[str] = []
        for topic in topics:
            keywords = self._topic_keywords(topic)
            if any(keyword in haystack for keyword in keywords):
                matched.append(topic)
        return matched

    def _matches_topics(self, item: RawHNItem, topics: list[str]) -> bool:
        """ Vérifie si l'article correspond à au moins un des topics recherchés """
        if not topics:
            return True
        return len(self._extract_matching_topics(item, topics)) > 0

    def _to_article_dict(self, item: RawHNItem, matched_topics: list[str]) -> dict[str, Any]:
        """ Convertit un RawHNItem en dictionnaire d'article """
        article = Article(
            id=str(item.id),
            title=item.title,
            source="hackernews",
            date=datetime.fromtimestamp(item.time, tz=timezone.utc),
            content=item.text or item.title,
            url=str(item.url) if item.url else f"https://news.ycombinator.com/item?id={item.id}",
            tags=matched_topics,
        )
        return article.model_dump()

    def _collect_matching_articles(self, story_ids: list[int], topics: list[str]) -> list[dict[str, Any]]:
        """ Collecte les articles correspondant aux topics donnés """
        articles: list[dict[str, Any]] = []
        for story_id in story_ids:
            item = self.get_item_details(story_id)
            if item is None:
                continue
            matched_topics = self._extract_matching_topics(item, topics)
            if not topics or matched_topics:
                articles.append(self._to_article_dict(item, matched_topics))
        return articles

    def run(self, topics: list[str]) -> list[dict[str, Any]]:
        settings = self.settings
        if settings is None:
            print("Settings unavailable")
            return []
    
        # 1. recuperer les derniers IDs Hacker News (sample de 5)
        top_stories = self.get_last_id(5)
        print(f"Fetched {len(top_stories)} story ids: {top_stories}")
        
        # 2. On récupère les détails de chaque article et on filtre par topic
        
        articles = self._collect_matching_articles(top_stories, topics)
        
        # 3. Afficher le nombre d'articles collectés et les topics associés
        print(f"Collected {len(articles)} articles matching topics {topics}")
        return articles
        
    
    
if __name__ == "__main__":
    ingester = NewsApiIngester()
    ingester.run(["technology", "programming"])
