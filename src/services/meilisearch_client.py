from typing import List, Dict, Any, Optional
import meilisearch
from src.config.settings import settings


class MeilisearchClient:
    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if MeilisearchClient._initialized:
            return
        
        self.client = meilisearch.Client(
            settings.meilisearch_host,
            settings.meilisearch_api_key if settings.meilisearch_api_key else None
        )
        self.index_name = settings.meilisearch_index
        self.embedder_name = "form-embedder"
        MeilisearchClient._initialized = True

    def get_index(self):
        return self.client.index(self.index_name)

    def setup_embedder(self) -> Dict[str, Any]:
        index = self.get_index()
        
        embedder_config = {
            self.embedder_name: {
                "source": "huggingFace",
                "model": "sentence-transformers/all-MiniLM-L6-v2",
                "documentTemplate": "A form template titled '{{doc.title}}'. {{doc.description}} {{doc.subTitle}}"
            }
        }
        
        task = index.update_embedders(embedder_config)
        return {"task_uid": task.task_uid, "status": "embedder configuration submitted"}

    def get_embedder_status(self) -> Dict[str, Any]:
        index = self.get_index()
        settings_data = index.get_settings()
        return settings_data.get("embedders", {})

    def get_task(self, task_uid: int) -> Dict[str, Any]:
        task = self.client.get_task(task_uid)
        return {
            "uid": task.uid,
            "status": task.status,
            "type": task.type,
            "started_at": str(task.started_at) if task.started_at else None,
            "finished_at": str(task.finished_at) if task.finished_at else None,
            "duration": task.duration,
            "error": task.error if hasattr(task, 'error') else None
        }

    def search(
        self,
        query: str,
        use_hybrid: bool = True,
        limit: int = 20,
        filters: Optional[str] = None
    ) -> Dict[str, Any]:
        index = self.get_index()
        
        search_params = {
            "limit": limit,
            "matchingStrategy": "last",
            "attributesToRetrieve": [
                "id", "title", "totalUsed", "internalNotes"
            ],
        }
        
        if filters:
            search_params["filter"] = filters
        
        if use_hybrid:
            embedders = self.get_embedder_status()
            if self.embedder_name in embedders:
                search_params["hybrid"] = {
                    "embedder": self.embedder_name,
                    "semanticRatio": 0.5
                }
        
        results = index.search(query, search_params)
        
        return {
            "query": query,
            "hits": results.get("hits", []),
            "total_hits": results.get("estimatedTotalHits", 0),
            "processing_time_ms": results.get("processingTimeMs", 0),
            "hybrid_enabled": "hybrid" in search_params
        }

    def semantic_search(
        self,
        query: str,
        limit: int = 10,
        filters: Optional[str] = None
    ) -> Dict[str, Any]:
        index = self.get_index()
        
        embedders = self.get_embedder_status()
        if self.embedder_name not in embedders:
            raise ValueError("Embedder not configured. Call setup_embedder first.")
        
        search_params = {
            "limit": limit,
            "attributesToRetrieve": [
                "id", "title", "totalUsed", "internalNotes"
            ],
            "hybrid": {
                "embedder": self.embedder_name,
                "semanticRatio": 1.0
            }
        }
        
        if filters:
            search_params["filter"] = filters
        
        results = index.search(query, search_params)
        
        return {
            "query": query,
            "hits": results.get("hits", []),
            "total_hits": results.get("estimatedTotalHits", 0),
            "processing_time_ms": results.get("processingTimeMs", 0),
            "search_type": "semantic"
        }

