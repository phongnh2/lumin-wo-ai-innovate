import os
from typing import List, Dict, Optional
import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer
from src.config.settings import settings


class VectorStore:
    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if VectorStore._initialized:
            return
        
        os.makedirs(settings.chroma_path, exist_ok=True)
        
        self.client = chromadb.PersistentClient(
            path=settings.chroma_path,
            settings=Settings(anonymized_telemetry=False)
        )
        
        self.collection = self.client.get_or_create_collection(
            name="pdf_documents",
            metadata={"hnsw:space": "cosine"}
        )
        
        self.embedder = SentenceTransformer('all-MiniLM-L6-v2')
        VectorStore._initialized = True

    def add_documents(self, chunks: List[Dict]) -> None:
        if not chunks:
            return
        
        ids = [chunk["id"] for chunk in chunks]
        texts = [chunk["text"] for chunk in chunks]
        metadatas = [{"source": chunk["source"], "chunk_index": chunk["chunk_index"]} for chunk in chunks]
        
        embeddings = self.embedder.encode(texts).tolist()
        
        self.collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=texts,
            metadatas=metadatas
        )

    def get_context_summary(self, n_samples: int = 10) -> Optional[str]:
        count = self.collection.count()
        
        if count == 0:
            return None
        
        results = self.collection.get(
            limit=min(n_samples, count),
            include=["documents"]
        )
        
        if not results["documents"]:
            return None
        
        return " ".join(results["documents"])

    def search(self, query: str, n_results: int = 5) -> List[Dict]:
        query_embedding = self.embedder.encode([query]).tolist()
        
        results = self.collection.query(
            query_embeddings=query_embedding,
            n_results=n_results,
            include=["documents", "metadatas", "distances"]
        )
        
        search_results = []
        for i in range(len(results["ids"][0])):
            search_results.append({
                "id": results["ids"][0][i],
                "text": results["documents"][0][i],
                "metadata": results["metadatas"][0][i],
                "distance": results["distances"][0][i]
            })
        
        return search_results

    def clear(self) -> None:
        self.client.delete_collection("pdf_documents")
        self.collection = self.client.get_or_create_collection(
            name="pdf_documents",
            metadata={"hnsw:space": "cosine"}
        )

