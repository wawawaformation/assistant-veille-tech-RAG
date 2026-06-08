# app/ingest

Ce dossier contient la logique d'ingestion des contenus sources (Hacker News, scraping, nettoyage) avant insertion dans Chroma.

## Fichiers

- news_api.py: pipeline principal de collecte Hacker News vers documents exploitables.
- scraper.py: scraping de pages externes (selon l'avancement du module).
- cleaning.py: fonctions de nettoyage/normalisation de contenu (selon l'avancement du module).
- enrich.py: enrichissement métier éventuel des contenus.
- topics.py: taxonomie et synonymes des topics.

## Focus: NewsApiIngester

La classe NewsApiIngester orchestre le flux complet:

1. Récupérer des IDs de stories Hacker News.
2. Charger les détails de chaque story.
3. Récupérer le contenu externe de la page cible.
4. Déterminer les topics correspondants.
5. Convertir en schéma Article.
6. Upsert dans Chroma.

### Méthodes et intérêt

- __post_init__: important. Injecte la configuration par défaut si absente.
- get_last_id: important. Point d'entrée API HN, sensible aux erreurs réseau/format.
- get_story_ids_page: important. Définit la pagination logique.
- get_item_details: important. Validation des payloads HN via Pydantic.
- _fetch_external_content: tres important. Extraction de contenu (trafilatura + fallback BeautifulSoup).
- _topic_keywords: utile. Ajoute les synonymes au topic de base.
- _contains_keyword: important. Evite les faux positifs avec bornes de mot.
- _extract_matching_topics: important. Filtre les contenus selon topics.
- _to_article: utile. Conversion vers le schema metier.
- _to_article_dict: utile. Serialization JSON-compatible.
- _collect_matching_articles: tres important. Boucle coeur de collecte + filtrage.
- _upsert_to_chroma: tres important. Ecriture d'un article complet en un seul document dans la base vectorielle.
- run: tres important. Orchestrateur public du pipeline.

## Choix techniques dans _fetch_external_content

- Tentative principale avec trafilatura (sortie markdown).
- Fallback BeautifulSoup lxml si trafilatura echoue ou extrait trop peu.
- Filtrage MIME assoupli: accepte aussi un body qui ressemble a du HTML.
- Seuil min_content_len pour eviter d'indexer du bruit.
- Politique newsletter: 1 article complet = 1 document Chroma (pas de chunking multi-parties).

## Tests

Tests acceptance existants:
- tests/acceptance/test_news_api_ingester.py

Tests unitaires ajoutes:
- tests/unit/test_news_api_ingester_unit.py

Lancer uniquement ces tests:

- uv run -m pytest tests/acceptance/test_news_api_ingester.py -vv
- uv run -m pytest tests/unit/test_news_api_ingester_unit.py -q
