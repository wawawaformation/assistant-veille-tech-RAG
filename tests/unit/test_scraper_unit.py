from __future__ import annotations

from typing import Any
from datetime import datetime

import requests
from bs4 import BeautifulSoup

from app.ingest.scraper import Scraper


class _FakeResponse:
    def __init__(self, content: bytes, status_code: int = 200) -> None:
        self.content = content
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


def test_safe_text_returns_default_when_node_is_none() -> None:
    scraper = Scraper()

    assert scraper._safe_text(None, "fallback") == "fallback"


def test_safe_text_returns_stripped_text_when_node_exists() -> None:
    scraper = Scraper()
    soup = BeautifulSoup("<h2>  Hello world  </h2>", "html.parser")
    node = soup.find("h2")

    assert node is not None
    assert scraper._safe_text(node, "fallback") == "Hello world"


def test_get_articles_list_keeps_only_complete_articles(monkeypatch: Any) -> None:
    html = """
    <html><body>
      <article>
        <h2 class="article-card-title">Article A</h2>
        <a data-href="https://example.com/a">Read</a>
        <time datetime="2026-06-08T11:45:29+02:00">Le 8 juin 2026</time>
      </article>
      <article>
        <h2 class="article-card-title">Article B</h2>
        <a href="https://example.com/b">Read</a>
        <time>Le 8 juin 2026</time>
      </article>
      <article>
        <h2 class="article-card-title">Missing date</h2>
        <a data-href="https://example.com/c">Read</a>
      </article>
      <article>
        <a data-href="https://example.com/d">Read</a>
        <time datetime="2026-06-08T09:08:51+02:00">Le 8 juin 2026</time>
      </article>
    </body></html>
    """.encode("utf-8")

    def fake_get(*args: Any, **kwargs: Any) -> _FakeResponse:
        return _FakeResponse(content=html)

    monkeypatch.setattr("app.ingest.scraper.requests.get", fake_get)
    monkeypatch.setattr(
        "app.ingest.scraper.Scraper._extract_text",
        lambda self, url: f"content for {url}",
    )
    monkeypatch.setattr(
        "app.ingest.scraper.Scraper._extract_tags",
        lambda self, url: ["Hackers Celebres"] if url.endswith("/a") else ["Actualites Securite"],
    )

    scraper = Scraper()
    articles = scraper.get_articles_list("https://example.com", howmany=10)

    assert len(articles) == 2

    assert articles[0].title == "Article A"
    assert str(articles[0].url) == "https://example.com/a"
    assert articles[0].date == datetime.fromisoformat("2026-06-08T11:45:29+02:00")
    assert articles[0].content == "content for https://example.com/a"
    assert articles[0].tags == ["Hackers Celebres"]

    assert articles[1].title == "Article B"
    assert str(articles[1].url) == "https://example.com/b"
    assert articles[1].date is None
    assert articles[1].content == "content for https://example.com/b"
    assert articles[1].tags == ["Actualites Securite"]


def test_get_articles_list_returns_empty_on_request_error(monkeypatch: Any) -> None:
    def fake_get(*args: Any, **kwargs: Any) -> _FakeResponse:
        raise requests.RequestException("network down")

    monkeypatch.setattr("app.ingest.scraper.requests.get", fake_get)

    scraper = Scraper()

    assert scraper.get_articles_list("https://example.com", howmany=5) == []
