import logging
from typing import Any, Dict, List, Optional

import meilisearch
import requests

from src.config.settings import settings

logger = logging.getLogger(__name__)

# Fields returned for list/card views
CARD_ATTRIBUTES = [
    "id", "title", "slug", "description", "categories",
    "thumbnails", "totalUsed", "accessible", "eSignCompatible",
    "legalReview", "outdated", "domain", "relatedFormByDomain",
    "countryCode", "stateCode", "file",
]

# Fields returned for the inline search bar (multi-search)
SEARCH_HIT_ATTRIBUTES = [
    "id", "title", "slug", "searchTerms", "categories",
]

EMBEDDER_NAME = "form-embedder"
EMBEDDER_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

FILTERABLE_ATTRIBUTES = [
    "domain", "language", "outdated", "eSignCompatible", "accessible",
    "legalReview", "publishedDateTimestamp", "publishedDate", "totalUsed",
    "amountUsed", "initUsed", "ranking", "countryCode", "stateCode",
    "categories.id", "categories.slug", "categories.name",
]

SORTABLE_ATTRIBUTES = [
    "ranking", "totalUsed", "publishedDate", "publishedDateTimestamp",
    "amountUsed", "outdated", "title",
]


class TemplateSearchService:
    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if TemplateSearchService._initialized:
            return
        self.client = meilisearch.Client(
            settings.meilisearch_host,
            settings.meilisearch_api_key if settings.meilisearch_api_key else None,
        )
        self.index_name = settings.meilisearch_index
        TemplateSearchService._initialized = True

    def get_index(self):
        return self.client.index(self.index_name)

    def configure_index(self) -> None:
        """Update index filterable/sortable settings. Fire-and-forget on startup."""
        try:
            index = self.get_index()
            index.update_filterable_attributes(FILTERABLE_ATTRIBUTES)
            index.update_sortable_attributes(SORTABLE_ATTRIBUTES)
            logger.info("Meilisearch index settings update submitted.")
        except Exception as e:
            logger.warning("Could not update Meilisearch index settings: %s", e)

    def setup_embedder_if_needed(self) -> None:
        """Enable vectorStore feature + register HuggingFace embedder if not already done."""
        try:
            headers = {"Content-Type": "application/json"}
            if settings.meilisearch_api_key:
                headers["Authorization"] = f"Bearer {settings.meilisearch_api_key}"

            resp = requests.patch(
                f"{settings.meilisearch_host}/experimental-features",
                json={"vectorStore": True},
                headers=headers,
                timeout=5,
            )
            if resp.status_code not in (200, 202):
                logger.warning("vectorStore enable returned %s: %s", resp.status_code, resp.text)

            index = self.get_index()
            existing = index.get_settings().get("embedders", {})
            if EMBEDDER_NAME not in existing:
                index.update_embedders({
                    EMBEDDER_NAME: {
                        "source": "huggingFace",
                        "model": EMBEDDER_MODEL,
                        "documentTemplate": (
                            "A form template titled '{{doc.title}}'. "
                            "{{doc.description}} {{doc.subTitle}}"
                        ),
                    }
                })
                logger.info("Embedder '%s' registration submitted.", EMBEDDER_NAME)
            else:
                logger.info("Embedder '%s' already configured.", EMBEDDER_NAME)
        except Exception as e:
            logger.warning("Embedder setup skipped: %s", e)

    def _do_search(self, query: str, params: Dict[str, Any]) -> Dict[str, Any]:
        index = self.get_index()
        raw = index.search(query, params)
        return {
            "hits": raw.get("hits", []),
            "query": raw.get("query", query),
            "processingTimeMs": raw.get("processingTimeMs", 0),
            "limit": raw.get("limit", params.get("limit", 24)),
            "offset": raw.get("offset", params.get("offset", 0)),
            "estimatedTotalHits": raw.get("estimatedTotalHits", 0),
            "facetDistribution": raw.get("facetDistribution", {}),
            "facetStats": raw.get("facetStats", {}),
        }

    def search(
        self,
        query: str,
        filter_expr: Optional[str] = None,
        sort: Optional[List[str]] = None,
        offset: int = 0,
        limit: int = 24,
        attributes_to_retrieve: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {
            "attributesToRetrieve": attributes_to_retrieve or CARD_ATTRIBUTES,
            "offset": offset,
            "limit": limit,
        }
        if filter_expr:
            params["filter"] = filter_expr
        if sort:
            params["sort"] = sort

        try:
            return self._do_search(query, params)
        except meilisearch.errors.MeilisearchApiError as e:
            err = str(e).lower()
            # Gracefully retry without sort/filter if index settings aren't ready yet
            if "filterable" in err or "sortable" in err or "invalid search" in err:
                logger.warning(
                    "Meilisearch rejected sort/filter (%s). Retrying without them. "
                    "Run `python scripts/import_forms.py` to fix permanently.",
                    e,
                )
                fallback: Dict[str, Any] = {
                    "attributesToRetrieve": attributes_to_retrieve or CARD_ATTRIBUTES,
                    "offset": offset,
                    "limit": limit,
                }
                return self._do_search(query, fallback)
            raise

    def get_by_id(self, template_id: int) -> Optional[Dict[str, Any]]:
        index = self.get_index()
        try:
            return index.get_document(template_id)
        except meilisearch.errors.MeilisearchApiError:
            return None

    def multi_search(self, query: str, limit: int = 10) -> Dict[str, Any]:
        """Single-index search shaped as Meilisearch multi-search response."""
        index = self.get_index()
        params: Dict[str, Any] = {
            "attributesToRetrieve": SEARCH_HIT_ATTRIBUTES,
            "attributesToHighlight": ["title", "subTitle", "searchTerms", "description"],
            "attributesToCrop": ["description"],
            "cropLength": 50,
            "limit": limit,
        }
        try:
            raw = index.search(query, params)
        except meilisearch.errors.MeilisearchApiError as e:
            logger.warning("multi_search error: %s", e)
            raw = {}

        return {
            "results": [
                {
                    "indexUid": self.index_name,
                    "hits": raw.get("hits", []),
                    "query": raw.get("query", query),
                    "processingTimeMs": raw.get("processingTimeMs", 0),
                    "limit": raw.get("limit", limit),
                    "offset": raw.get("offset", 0),
                    "estimatedTotalHits": raw.get("estimatedTotalHits", 0),
                }
            ]
        }
