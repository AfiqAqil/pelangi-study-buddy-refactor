"""Simplified Qdrant vector store integration."""

import asyncio
from typing import List, Dict, Any, Optional

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Distance, VectorParams

from app.core.config import settings
from app.core.logging import logger


class QdrantVectorStore:
    """Simplified Qdrant vector store manager."""
    
    def __init__(self):
        """Initialize Qdrant vector store."""
        self._client: Optional[AsyncQdrantClient] = None
        self._collection_name = settings.QDRANT_COLLECTION
        
        logger.debug(
            "qdrant_vector_store_initialized",
            collection=self._collection_name,
            url=settings.QDRANT_URL,
        )
    
    def _create_client(self) -> AsyncQdrantClient:
        """Create Qdrant client with basic configuration."""
        if not settings.QDRANT_URL:
            raise ValueError("QDRANT_URL not configured")
        
        client_kwargs = {"url": settings.QDRANT_URL}
        
        if settings.QDRANT_PORT:
            client_kwargs["port"] = settings.QDRANT_PORT
        if settings.QDRANT_KEY:
            client_kwargs["api_key"] = settings.QDRANT_KEY
        
        return AsyncQdrantClient(**client_kwargs)
    
    async def get_client(self) -> AsyncQdrantClient:
        """Get async Qdrant client instance.
        
        Returns:
            AsyncQdrantClient: Configured client
        """
        if self._client is None:
            try:
                self._client = self._create_client()
                # Test connection
                await self._client.get_collections()
                logger.info("qdrant_client_connected", url=settings.QDRANT_URL)
            except Exception as e:
                logger.error("qdrant_connection_failed", error=str(e))
                raise RuntimeError(f"Failed to connect to Qdrant: {e}") from e
        
        return self._client
    
    
    async def ensure_collection_exists(self) -> bool:
        """Ensure the collection exists with basic configuration."""
        try:
            client = await self.get_client()
            collections = await client.get_collections()
            
            # Check if collection already exists
            existing_collections = [c.name for c in collections.collections]
            if self._collection_name in existing_collections:
                logger.info("collection_exists", collection=self._collection_name)
                return True
            
            # Create collection with basic settings
            await client.create_collection(
                collection_name=self._collection_name,
                vectors_config=VectorParams(
                    size=768,  # Qwen embedding dimensions
                    distance=Distance.COSINE,
                )
            )
            
            logger.info("collection_created", collection=self._collection_name)
            return True
            
        except Exception as e:
            logger.error("collection_setup_failed", error=str(e))
            return False
    
    
    async def search_similar(
        self,
        query_vector: List[float],
        top_k: int = None,
        score_threshold: float = None,
    ) -> List[Dict[str, Any]]:
        """Search for similar vectors.
        
        Args:
            query_vector: Query embedding vector
            top_k: Number of results to return
            score_threshold: Minimum similarity score
            
        Returns:
            List[Dict[str, Any]]: Search results with metadata
        """
        try:
            client = await self.get_client()
            
            # Use configured defaults if not provided
            top_k = top_k or settings.RAG_SIMILARITY_TOP_K
            score_threshold = score_threshold or settings.RAG_SIMILARITY_CUTOFF
            
            # Search without filtering to avoid index requirements
            results = await client.search(
                collection_name=self._collection_name,
                query_vector=query_vector,
                limit=top_k,
                score_threshold=score_threshold,
                with_payload=True,
                with_vectors=False,
            )
            
            # Format results
            formatted_results = []
            for result in results:
                formatted_results.append({
                    "id": result.id,
                    "score": result.score,
                    "payload": result.payload,
                    "text": result.payload.get("text", ""),
                    "source": result.payload.get("source", ""),
                    "page_num": result.payload.get("page_num"),
                    "chapter": result.payload.get("chapter"),
                })
            
            logger.debug(
                "vector_search_completed",
                results_count=len(formatted_results),
                top_k=top_k,
                score_threshold=score_threshold,
            )
            
            return formatted_results
            
        except Exception as e:
            logger.error("vector_search_failed", error=str(e))
            return []
    
    async def test_connection(self) -> bool:
        """Test Qdrant connection and collection access.
        
        Returns:
            bool: True if connection is successful
        """
        try:
            client = await self.get_client()
            collections = await client.get_collections()
            
            # Test if our collection exists
            collection_names = [c.name for c in collections.collections]
            collection_exists = self._collection_name in collection_names
            
            logger.info(
                "qdrant_connection_test",
                success=True,
                collection_exists=collection_exists,
                total_collections=len(collection_names),
            )
            
            return True
            
        except Exception as e:
            logger.error("qdrant_connection_test_failed", error=str(e))
            return False
    
    
    async def close(self):
        """Close client connection."""
        if self._client:
            try:
                await self._client.close()
                logger.info("qdrant_client_closed")
            except Exception as e:
                logger.error("qdrant_client_close_failed", error=str(e))
            finally:
                self._client = None


# Global vector store instance
_vector_store = None

async def get_vector_store() -> QdrantVectorStore:
    """Get global vector store instance."""
    global _vector_store
    if _vector_store is None:
        _vector_store = QdrantVectorStore()
    return _vector_store