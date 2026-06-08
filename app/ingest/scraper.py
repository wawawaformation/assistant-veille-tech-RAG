from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from bs4 import BeautifulSoup
import requests
import trafilatura
from app.logger import AppLogger
from app.schemas import ArticleScraping


logger = AppLogger.get_logger(__name__, log_file="scraper.log")


@dataclass
class Scraper:
    user_agent: str = "nauda-palisse-veille/0.1"
    timeout: float = 10.0

    def _safe_text(self, node: Any, default: str) -> str:
        """Retourne le texte d'un noeud BS4, ou une valeur par defaut s'il est absent."""

        if node is None:
            return default

        return node.get_text(strip=True)
    
    def _extract_text(self, url: str) -> str:
        """ Retourne le contenu HTML d'une page web """

        html = trafilatura.fetch_url(url)
        if html is None:
            logger.warning("Impossible de recuperer le contenu HTML pour %s", url)
            return ""

        extracted = trafilatura.extract(html) or ""

        if not extracted:
            logger.info("Aucun contenu extrait pour %s", url)

        return extracted
    
    def _extract_tags(self, article_url: str) -> list[str]:
        """Extrait les sous-categories d'un article (ex: Hackers Celebres). Attention que pour Korben"""

        try:
            response = requests.get(
                article_url,
                headers={"User-Agent": self.user_agent},
                timeout=self.timeout,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            logger.warning("Impossible de recuperer les tags pour %s: %s", article_url, exc)
            return []

        soup = BeautifulSoup(response.content, "html.parser")
        tag_nodes = soup.select(".article-subcategories-details a")

        tags: list[str] = []
        for node in tag_nodes:
            tag = self._safe_text(node, "")
            if tag and tag not in tags:
                tags.append(tag)

        return tags
    
    
    def _extract_article_url(self, link_node: Any) -> str:
        """Extrait et normalise l'URL depuis un noeud lien."""

        if not link_node:
            return ""

        raw_url = link_node.get("data-href") or link_node.get("href", "")

        if isinstance(raw_url, list):
            return str(raw_url[0]).strip() if raw_url else ""

        return str(raw_url).strip()

    def _extract_card_published(self, article_node: Any) -> str:
        """Extrait la date depuis la carte d'article de la page listing."""

        published_node = article_node.find(class_="article-card-date")
        time_node = article_node.find("time")
        published = self._safe_text(published_node, "")

        if not published and time_node:
            raw_published = time_node.get("datetime", "") or self._safe_text(time_node, "")
            if isinstance(raw_published, list):
                return str(raw_published[0]).strip() if raw_published else ""
            return str(raw_published).strip()

        return published.strip()

    def _to_datetime_or_none(self, raw: str) -> datetime | None:
        """Convertit une date texte en datetime si possible."""

        value = raw.strip()
        if not value:
            return None

        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None

    def _build_article_from_node(self, article_node: Any) -> ArticleScraping | None:
        """Construit un ArticleScraping depuis un noeud article ou retourne None."""

        title = self._safe_text(article_node.find(class_="article-card-title"), "")
        link_node = article_node.select_one("[data-href]") or article_node.find("a", href=True)
        url_value = self._extract_article_url(link_node)
        published = self._extract_card_published(article_node)

        if not title or not url_value or not published:
            logger.debug(
                "Article ignore car incomplet (title=%s, url=%s, published=%s)",
                bool(title),
                bool(url_value),
                bool(published),
            )
            return None

        return self.format_article(
            {
                "title": title,
                "url": url_value,
                "published": published,
                "content": self._extract_text(url_value),
                "tags": self._extract_tags(url_value),
            }
        )

    def format_article(self, article: dict[str, Any]) -> ArticleScraping:
        """Formate et valide un article brut selon le schema ArticleScraping."""
        return ArticleScraping(
            title=article.get("title", "").strip(),
            url=article.get("url", "").strip(),
            date=self._to_datetime_or_none(str(article.get("published", ""))),
            content=article.get("content", "").strip(),
            tags=article.get("tags", []),
        )
    
    
    def get_articles_list(self, url: str, howmany: int) -> list[ArticleScraping]:
        """Retourne une liste d'articles scrapes et valides."""

        try:
            response = requests.get(
                url,
                headers={"User-Agent": self.user_agent},
                timeout=self.timeout,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            logger.warning("Erreur HTTP pendant le scraping de %s: %s", url, exc)
            return []

        soup = BeautifulSoup(response.content, "html.parser")
        articles: list[ArticleScraping] = []

        for article_node in soup.find_all("article")[:howmany]:
            article = self._build_article_from_node(article_node)
            if article is not None:
                articles.append(article)

        return articles


    def run(self, urls: list[str]) -> list[ArticleScraping]:
        """ Lance le scrapping de la premiere url fournie pour instant"""
        if not urls:
            logger.warning("Aucune URL fournie au scraper")
            return []

        logger.info("Demarrage scraping url=%s howmany=%s", urls[0], 5)
        articles = self.get_articles_list(urls[0], 5)
        logger.info("Scraping termine: %s article(s) collecte(s)", len(articles))

        for article in articles:
            print(f"Title: {article.title}")
            print(f"URL: {article.url}")
            print(f"Published: {article.date}")
            print(f"Content: {article.content}...")
            print("-" * 80)
        return articles
        
        
        


if __name__ == "__main__":
    scraper = Scraper()
    scraper.run(["https://korben.info/"])