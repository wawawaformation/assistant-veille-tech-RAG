from __future__ import annotations

import json
import sys
from pathlib import Path

import typer

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.ingest.news_api import NewsApiIngester

app = typer.Typer(help="Ingestion CLI for the veille tech index.")


@app.command()
def news(topics: list[str] = typer.Option([], "--topic", "-t", help="Topic to query.")) -> None:
    ingester = NewsApiIngester()
    articles = ingester.run(topics)
    typer.echo(f"Ingested {len(articles)} articles")
    typer.echo(json.dumps(articles, default=str, ensure_ascii=False, indent=2))


@app.command()
def scrape(urls: list[str] = typer.Option(..., "--url", "-u", help="URL to scrape.")) -> None:
    typer.echo(
        "scrape command is not wired yet because app.ingest.scraper.Scraper.run is not implemented."
    )
    typer.echo(f"Received {len(urls)} URLs: {urls}")
    raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
