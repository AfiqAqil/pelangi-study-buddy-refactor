"""Simplified RAG tools for LangGraph integration."""

import asyncio
from typing import Dict, Any, Optional, List

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from app.core.rag.service import get_rag_service
from app.core.logging import logger


class QdrantRetrieverInput(BaseModel):
    """Input schema for Qdrant retriever tool."""
    
    query: str = Field(description="The search query for retrieving relevant documents")
    top_k: Optional[int] = Field(default=None, description="Number of documents to retrieve")
    score_threshold: Optional[float] = Field(default=None, description="Minimum similarity score threshold")


class GenerateRAGAnswerInput(BaseModel):
    """Input schema for RAG answer generation tool."""
    
    question: str = Field(description="The user's question to answer")
    language: str = Field(default="en", description="Language for the response (en, ms, zh)")


class ComprehensiveRAGSearchInput(BaseModel):
    """Input schema for comprehensive RAG search tool."""
    
    question: str = Field(description="The user's question for comprehensive RAG search")
    language: str = Field(default="en", description="Language for the response (en, ms, zh)")
    session_id: Optional[str] = Field(default=None, description="Optional session ID for conversation memory")


class QdrantRetrieverTool(BaseTool):
    """Tool for direct semantic search."""
    
    name: str = "qdrant_retriever"
    description: str = (
        "Performs semantic search on the knowledge base using vector similarity. "
        "Use this to find relevant documents based on a query."
    )
    args_schema: type[BaseModel] = QdrantRetrieverInput
    
    def _run(self, **kwargs) -> str:
        """Execute the Qdrant retriever tool synchronously."""
        import asyncio
        return asyncio.run(self._arun(**kwargs))
    
    async def _arun(self, **kwargs) -> str:
        """Execute the Qdrant retriever tool asynchronously."""
        try:
            from app.core.config import settings
            
            query = kwargs.get("query", "")
            top_k = kwargs.get("top_k") or settings.RAG_SIMILARITY_TOP_K
            score_threshold = kwargs.get("score_threshold") or settings.RAG_SIMILARITY_CUTOFF
            
            # Validate query input
            if not query or not query.strip():
                return "Please provide a search query to retrieve relevant documents."
            
            query = query.strip()
            
            logger.debug(
                "qdrant_retriever_called",
                query=query[:100],
                top_k=top_k,
                score_threshold=score_threshold,
            )
            
            # Use RAG service for document search
            rag_service = get_rag_service()
            results = await rag_service.search_documents(
                query=query,
                top_k=top_k,
                score_threshold=score_threshold
            )
            
            if not results:
                return "No relevant documents found for the query."
            
            # Format results
            formatted_results = []
            for i, result in enumerate(results):
                formatted_results.append({
                    "rank": i + 1,
                    "score": round(result["score"], 3),
                    "text": result["text"][:500] + "..." if len(result["text"]) > 500 else result["text"],
                    "source": result.get("source", ""),
                    "page": result.get("page_num", ""),
                    "chapter": result.get("payload", {}).get("chapter", ""),
                })
            
            return f"Found {len(results)} relevant documents:\n\n" + "\n\n".join([
                f"[{r['rank']}] Score: {r['score']}\nSource: {r['source']} (Page {r['page']})\nText: {r['text']}"
                for r in formatted_results
            ])
            
        except Exception as e:
            logger.error("qdrant_retriever_failed", error=str(e))
            return f"Error retrieving documents: {str(e)}"


class GenerateRAGAnswerTool(BaseTool):
    """Tool for multi-language answer generation using RAG."""
    
    name: str = "generate_rag_answer"
    description: str = (
        "Generates comprehensive answers using retrieval-augmented generation. "
        "This tool retrieves relevant documents and uses them to generate accurate, contextual answers. "
        "Supports multiple languages (English, Bahasa Malaysia, Chinese)."
    )
    args_schema: type[BaseModel] = GenerateRAGAnswerInput
    
    def _run(self, **kwargs) -> str:
        """Execute RAG answer generation synchronously."""
        import asyncio
        return asyncio.run(self._arun(**kwargs))
    
    async def _arun(self, **kwargs) -> str:
        """Execute RAG answer generation asynchronously."""
        try:
            question = kwargs.get("question", "")
            language = kwargs.get("language", "en")
            
            # Validate question input
            if not question or not question.strip():
                return "I need a question to provide an answer. Please ask me something about your studies."
            
            question = question.strip()
            
            logger.debug(
                "generate_rag_answer_called",
                question=question[:100],
                language=language,
            )
            
            # Use RAG service for answer generation
            rag_service = get_rag_service()
            result = await rag_service.generate_answer(
                query=question,
                language=language
            )
            
            if "error" in result:
                return f"Error generating answer: {result['error']}"
            
            answer = result.get("answer", "")
            citations = result.get("citations", [])
            
            # Format response with citations
            response_parts = [answer]
            
            if citations:
                response_parts.append("\n\nSources:")
                for citation in citations:
                    source_info = f"[{citation['index']}] {citation['source']}"
                    if citation.get('page'):
                        source_info += f" (Page {citation['page']})"
                    response_parts.append(source_info)
            
            return "\n".join(response_parts)
            
        except Exception as e:
            logger.error("generate_rag_answer_failed", error=str(e))
            return f"Error generating answer: {str(e)}"


class ComprehensiveRAGSearchTool(BaseTool):
    """Tool for full RAG pipeline with memory integration."""
    
    name: str = "comprehensive_rag_search"
    description: str = (
        "Performs comprehensive RAG search with full pipeline including retrieval, "
        "spatial image association, answer generation, and conversation memory. "
        "This is the most complete RAG tool that maintains conversation context and provides detailed responses."
    )
    args_schema: type[BaseModel] = ComprehensiveRAGSearchInput
    
    def _run(self, **kwargs) -> str:
        """Execute comprehensive RAG search synchronously."""
        import asyncio
        return asyncio.run(self._arun(**kwargs))
    
    async def _arun(self, **kwargs) -> str:
        """Execute comprehensive RAG search asynchronously."""
        try:
            question = kwargs.get("question", "")
            language = kwargs.get("language", "en")
            session_id = kwargs.get("session_id")
            
            # Validate question input
            if not question or not question.strip():
                return "I need a question to provide a comprehensive answer. Please ask me something about your studies."
            
            question = question.strip()
            
            logger.info(
                "comprehensive_rag_search_called",
                question=question[:100],
                language=language,
                session_id=session_id,
            )
            
            # Use RAG service for comprehensive search
            rag_service = get_rag_service()
            result = await rag_service.ask_question(
                query=question,
                language=language
            )
            
            if "error" in result:
                return f"Error in comprehensive search: {result['error']}"
            
            # Format comprehensive response
            answer = result.get("answer", "")
            citations = result.get("citations", [])
            context_used = result.get("context_used", 0)
            
            response_parts = [answer]
            
            # Add metadata
            metadata_parts = []
            if context_used > 0:
                metadata_parts.append(f"Context sources: {context_used}")
            if language != "en":
                metadata_parts.append(f"Language: {language}")
            
            if metadata_parts:
                response_parts.append(f"\nSearch details: {', '.join(metadata_parts)}")
            
            # Add citations with enhanced information
            if citations:
                response_parts.append("\n\nDetailed sources:")
                for citation in citations:
                    source_info = f"[{citation['index']}] {citation['source']}"
                    if citation.get('page'):
                        source_info += f" (Page {citation['page']})"
                    if citation.get('score'):
                        source_info += f" - Relevance: {citation['score']:.3f}"
                    
                    response_parts.append(source_info)
                    
                    # Add text preview
                    if citation.get('text_preview'):
                        response_parts.append(f"    Preview: {citation['text_preview']}")
                    
            
            return "\n".join(response_parts)
            
        except Exception as e:
            logger.error("comprehensive_rag_search_failed", error=str(e))
            return f"Error in comprehensive search: {str(e)}"


# Tool instances
qdrant_retriever_tool = QdrantRetrieverTool()
generate_rag_answer_tool = GenerateRAGAnswerTool()
comprehensive_rag_search_tool = ComprehensiveRAGSearchTool()


# List of RAG tools for easy import
rag_tools = [
    qdrant_retriever_tool,
    generate_rag_answer_tool, 
    comprehensive_rag_search_tool,
]