from __future__ import annotations

from typing import Any
from bs4 import BeautifulSoup
from markdownify import markdownify
import trafilatura


def clean_html_to_markdown(html: str) -> str:
    """Nettoie le HTML et le convertit en Markdown"""
    downloaded = trafilatura.extract(html, output_format="markdown")
    if downloaded:
        return downloaded.strip()
   
    # fallback car trafilatura peut échouer sur du HTML mal formé
    return markdownify(html, heading_style="ATX").strip()


def dedupe(articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Supprime les articles en double basés sur l'URL"""
    seen_urls = set()
    deduped = []
    for art in articles:
        url = art.get("url")
        if url and url not in seen_urls:
            seen_urls.add(url)
            deduped.append(art)
    return deduped


def chunk(text: str, max_chars: int = 1200, overlap_chars: int = 200) -> list[str]:
    """Découpe le texte en chunks avec chevauchement sur des mots complets."""
    words = text.split()
    if not words:
        return []

    if max_chars <= 0:
        raise ValueError("max_chars must be > 0")

    overlap_chars = max(0, min(overlap_chars, max_chars - 1))
    chunks: list[str] = []
    i = 0

    while i < len(words):
        current_words: list[str] = []
        current_len = 0
        j = i

        while j < len(words):
            word = words[j]
            extra = len(word) if not current_words else len(word) + 1
            if current_len + extra > max_chars:
                break
            current_words.append(word)
            current_len += extra
            j += 1

        if not current_words:
            # Mot plus long que max_chars: on le place seul pour eviter une boucle infinie.
            current_words = [words[i]]
            j = i + 1

        chunks.append(" ".join(current_words))

        if j >= len(words):
            break

        if overlap_chars == 0:
            i = j
            continue

        overlap_len = 0
        back = j - 1
        while back > i:
            token_len = len(words[back]) if overlap_len == 0 else len(words[back]) + 1
            if overlap_len + token_len > overlap_chars:
                break
            overlap_len += token_len
            back -= 1

        i = back + 1

    return chunks


def strip_boilerplate(soup: BeautifulSoup) -> BeautifulSoup:
    """Supprime les éléments inutiles pour ne garder que la partie centrale du contenu"""
    for selector in ("nav", "footer", "header", "aside", "script", "style", "form", "button"):
        for node in soup.select(selector):
            node.decompose()
    return soup
    
    




