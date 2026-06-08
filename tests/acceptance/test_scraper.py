from __future__ import annotations

from app.ingest.scraper import Scraper
from app.schemas import ArticleScraping


def test_run_returns_articles_with_required_fields() -> None:
    scraper = Scraper()
    articles = scraper.run(["https://example.com/changelog"])
    assert isinstance(articles, list)
    for art in articles:
        assert isinstance(art, ArticleScraping)
        assert art.title
        assert str(art.url)
        assert isinstance(art.content, str)


def test_run_handles_unreachable_url_gracefully() -> None:
    scraper = Scraper()
    out = scraper.run(["http://127.0.0.1:1/does-not-exist"])
    assert isinstance(out, list)
