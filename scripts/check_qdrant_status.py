#!/usr/bin/env python3
"""Check Qdrant collection status and search for test content."""

import asyncio
from app.core.rag.vector_store import get_vector_store
from app.core.rag.model_manager import get_model_manager
from app.core.config import settings

async def check_qdrant_status():
    """Check Qdrant collection and test search."""
    try:
        print(f"🔍 Checking Qdrant collection: {settings.QDRANT_COLLECTION}")
        print(f"🎯 Using threshold: {settings.RAG_SIMILARITY_CUTOFF}")
        
        # Get vector store and model manager
        vector_store = await get_vector_store()
        model_manager = get_model_manager()
        
        # Test connection
        print("\n📡 Testing Qdrant connection...")
        connection_ok = await vector_store.test_connection()
        print(f"   Connection: {'✅ OK' if connection_ok else '❌ Failed'}")
        
        if not connection_ok:
            return
        
        # Test embedding model
        print("\n🤖 Testing embedding model...")
        embedding_model = model_manager.get_embedding_model()
        test_query = "What is Newton's first law"
        query_embedding = await asyncio.to_thread(
            embedding_model.get_text_embedding, test_query
        )
        print(f"   Embedding generated: ✅ {len(query_embedding)} dimensions")
        
        # Test search with different thresholds
        print(f"\n🔎 Searching for: '{test_query}'")
        
        thresholds = [0.5, 0.3, 0.1, 0.0]
        for threshold in thresholds:
            print(f"\n   📊 Testing threshold {threshold}:")
            results = await vector_store.search_similar(
                query_vector=query_embedding,
                top_k=5,
                score_threshold=threshold
            )
            print(f"      Results: {len(results)} documents found")
            
            if results:
                for i, result in enumerate(results[:3]):
                    print(f"      [{i+1}] Score: {result['score']:.3f}")
                    print(f"          Text: {result['text'][:100]}...")
                break
        
        if not any(results for threshold in [0.5, 0.3, 0.1, 0.0]):
            print("\n❌ No results found at any threshold!")
            print("   This suggests your Qdrant collection is empty or doesn't contain relevant content.")
            print("   You need to add documents about Newton's laws and physics concepts.")
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    asyncio.run(check_qdrant_status())