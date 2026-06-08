from __future__ import annotations

import json
import sys
from pathlib import Path

import typer

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.ingest.news_api import NewsApiIngester
from app.ingest.scraper import Scraper

app = typer.Typer(help="Ingestion CLI for the veille tech index.")


@app.command()
def news(topics: list[str] = typer.Option([], "--topic", "-t", help="Topic to query.")) -> None:
    ingester = NewsApiIngester()
    articles = ingester.run(topics)
    typer.echo(f"Ingested {len(articles)} articles")
    typer.echo(json.dumps(articles, default=str, ensure_ascii=False, indent=2))


@app.command()
def scrape(
    urls: list[str] = typer.Option(..., "--url", "-u", help="URL to scrape."),
    howmany: int = typer.Option(5, "--howmany", "-n", help="Max articles per URL."),
) -> None:
    if howmany <= 0:
        raise typer.BadParameter("--howmany must be a positive integer")

    scraper = Scraper()
    all_articles = []

    for url in urls:
        all_articles.extend(scraper.get_articles_list(url, howmany=howmany))

    payload = [article.model_dump(mode="json") for article in all_articles]

    typer.echo(f"Scraped {len(payload)} articles from {len(urls)} URL(s)")
    typer.echo(json.dumps(payload, default=str, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    app()
