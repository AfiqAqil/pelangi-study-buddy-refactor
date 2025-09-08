"""Simplified RAG service for educational content retrieval and generation."""

import json
import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime

from app.core.config import settings
from app.core.logging import logger
from app.utils.prompt_utils import get_prompt_template, format_prompt


class RAGService:
    """Simple RAG service that handles document retrieval and answer generation."""
    
    def __init__(self):
        """Initialize the RAG service."""
        # Components are pre-initialized at server startup
        pass
        
    def _get_model_manager(self):
        """Get pre-initialized model manager."""
        from app.core.rag.model_manager import get_model_manager
        return get_model_manager()
    
    async def _get_vector_store(self):
        """Get pre-initialized vector store."""
        from app.core.rag.vector_store import get_vector_store
        return await get_vector_store()
    
    def _detect_language(self, text: str) -> str:
        """Simple language detection."""
        if not text:
            return "en"
        
        # Check for Chinese characters
        chinese_chars = sum(1 for char in text if '\u4e00' <= char <= '\u9fff')
        if chinese_chars > len(text) * 0.1:
            return "zh"
        
        # Check for common Malay words
        malay_words = ['adalah', 'dengan', 'yang', 'untuk', 'dalam', 'pada', 'tidak', 'saya']
        words = text.lower().split()
        if words and any(word in malay_words for word in words):
            malay_count = sum(1 for word in words if word in malay_words)
            if malay_count / len(words) > 0.1:
                return "ms"
        
        return "en"
    
    def _is_educational_content(self, query: str, subject_context: Optional[Dict] = None) -> bool:
        """Simple educational content detection."""
        query_lower = query.lower()
        
        # Skip obvious conversational content
        conversation_patterns = [
            'hello', 'hi', 'how are you', 'good morning', 'thank you', 'bye',
            'halo', 'apa khabar', 'terima kasih', 'selamat',
            '你好', '谢谢', '再见', '你好吗'
        ]
        
        if any(pattern in query_lower for pattern in conversation_patterns):
            return False
        
        # Check for educational indicators
        educational_keywords = [
            # Question words with academic context
            'what is', 'how does', 'why does', 'explain', 'define', 'calculate',
            'apa itu', 'bagaimana', 'mengapa', 'terangkan', 'takrifkan', 'kira',
            '什么是', '如何', '为什么', '解释', '定义', '计算',
            
            # Subject-specific terms
            'formula', 'equation', 'process', 'function', 'system',
            'formula', 'persamaan', 'proses', 'fungsi', 'sistem',
            '公式', '方程', '过程', '功能', '系统',
            
            # Academic references
            'textbook', 'chapter', 'exercise', 'spm', 'form',
            'buku teks', 'bab', 'latihan', 'tingkatan',
            '教科书', '章节', '练习'
        ]
        
        # Check if query contains educational keywords
        if any(keyword in query_lower for keyword in educational_keywords):
            return True
        
        # Check subject-specific keywords if context available
        if subject_context and subject_context.get('current_subject'):
            subject_keywords = {
                'biology': ['cell', 'photosynthesis', 'dna', 'evolution', 'ecosystem'],
                'chemistry': ['atom', 'molecule', 'reaction', 'acid', 'element'],
                'physics': ['force', 'energy', 'wave', 'electricity', 'motion'],
                'mathematics': ['equation', 'function', 'graph', 'algebra', 'geometry']
            }
            
            subject = subject_context['current_subject'].lower()
            if subject in subject_keywords:
                if any(keyword in query_lower for keyword in subject_keywords[subject]):
                    return True
        
        return False
    
    async def search_documents(
        self, 
        query: str,
        top_k: int = None,
        score_threshold: float = None
    ) -> List[Dict[str, Any]]:
        """Search for relevant documents."""
        try:
            model_manager = self._get_model_manager()
            vector_store = await self._get_vector_store()
            
            # Get query embedding
            embedding_model = model_manager.get_embedding_model()
            query_embedding = await asyncio.to_thread(
                embedding_model.get_text_embedding, query
            )
            
            # Search vector store
            top_k = top_k or settings.RAG_SIMILARITY_TOP_K
            score_threshold = score_threshold or settings.RAG_SIMILARITY_CUTOFF
            
            results = await vector_store.search_similar(
                query_vector=query_embedding,
                top_k=top_k,
                score_threshold=score_threshold
            )
            
            logger.debug(
                "rag_search_completed",
                query=query[:100],
                results_count=len(results)
            )
            
            return results
            
        except Exception as e:
            logger.error("rag_search_failed", error=str(e), query=query[:100])
            return []
    
    async def generate_answer(
        self,
        query: str,
        documents: Optional[List[Dict[str, Any]]] = None,
        language: Optional[str] = None
    ) -> Dict[str, Any]:
        """Generate answer using retrieved documents."""
        try:
            # Auto-detect language if not provided
            if not language:
                language = self._detect_language(query)
            
            # Search documents if not provided
            if documents is None:
                documents = await self.search_documents(query)
            
            # Prepare context from documents
            context_parts = []
            citations = []
            
            # Use top documents for context
            max_docs = min(len(documents), settings.RAG_RERANKED_TOP_N or 5)
            for i, doc in enumerate(documents[:max_docs]):
                text = json.loads(doc['payload']['_node_content']).get('text')
                source = doc.get("source", "")
                page_num = doc.get("page_num", "")
                score = doc.get("score", 0.0)
                
                context_parts.append(f"[{i+1}] {text}")
                citations.append({
                    "index": i + 1,
                    "source": source,
                    "page": page_num,
                    "score": score,
                    "text_preview": text[:100] + "..." if len(text) > 100 else text
                })
            
            # Create context
            context = "\n\n".join(context_parts)
            
            # Get language-specific prompt template and format it
            template = get_prompt_template('rag_prompts.yaml', 'rag_prompts', language)
            formatted_prompt = format_prompt(template, query=query, context=context)
            
            # Generate response
            model_manager = self._get_model_manager()
            llm_model = model_manager.get_llm_model()
            
            response = await llm_model.acomplete(formatted_prompt)

            logger.info(
                "rag_answer_generated",
                query=query[:100],
                formatted_prompt=formatted_prompt[:300],
                response=response.text[:300],
            )
            result = {
                "answer": response.text,
                "citations": citations,
                "context_used": len(context_parts),
                "language": language,
                "query": query,
                "timestamp": datetime.utcnow().isoformat()
            }
            
            return result
            
        except Exception as e:
            logger.error("rag_answer_generation_failed", error=str(e), query=query[:100])
            return {
                "answer": "I apologize, but I encountered an error while generating a response.",
                "citations": [],
                "error": str(e),
                "query": query
            }
    
    async def ask_question(
        self,
        query: str,
        language: Optional[str] = None,
        subject_context: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Complete RAG pipeline: search documents and generate answer."""
        try:
            # Validate input
            if not query or not query.strip():
                return {
                    "answer": "Please provide a question for me to answer.",
                    "citations": [],
                    "context_used": 0,
                    "error": "empty_query"
                }
            
            query = query.strip()
            
            # Check if this is educational content
            is_educational = self._is_educational_content(query, subject_context)
            
            if not is_educational:
                logger.debug("non_educational_query", query=query[:100])
                return {
                    "answer": "This appears to be a general conversation. For educational questions about your textbooks, please ask specific questions about subjects like Biology, Chemistry, Physics, or Mathematics.",
                    "citations": [],
                    "context_used": 0,
                    "content_type": "general_conversation"
                }
            
            # Auto-detect language
            if not language:
                language = self._detect_language(query)
            
            logger.info(
                "rag_question_processing",
                query=query[:100],
                language=language,
                is_educational=is_educational
            )
            
            # Generate answer using full pipeline
            result = await self.generate_answer(query, None, language)
            result["content_type"] = "educational"
            
            return result
            
        except Exception as e:
            logger.error("rag_ask_question_failed", error=str(e), query=query[:100])
            return {
                "answer": "I encountered an error while processing your question.",
                "citations": [],
                "error": str(e),
                "query": query
            }


# Global service instance
_rag_service = None

def get_rag_service() -> RAGService:
    """Get global RAG service instance."""
    global _rag_service
    if _rag_service is None:
        _rag_service = RAGService()
    return _rag_service