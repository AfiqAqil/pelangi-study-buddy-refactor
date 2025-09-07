"""LangGraph tools for enhanced language model capabilities.

This package contains custom tools that can be used with LangGraph to extend
the capabilities of language models. Currently includes tools for web search,
subject selection, and RAG (Retrieval-Augmented Generation).
"""

from langchain_core.tools.base import BaseTool

from .duckduckgo_search import duckduckgo_search_tool
from .subject_selection import subject_selection_tool, subject_context_tool

# Import RAG tools conditionally based on configuration
try:
    from app.core.config import settings
    if settings.RAG_ENABLED:
        # Import RAG tools without initializing workflow to avoid startup issues
        from .rag_tools import qdrant_retriever_tool, generate_rag_answer_tool, comprehensive_rag_search_tool
        tools: list[BaseTool] = [
            duckduckgo_search_tool,
            subject_selection_tool,
            subject_context_tool,
            qdrant_retriever_tool,
            generate_rag_answer_tool,
            comprehensive_rag_search_tool,
        ]
    else:
        tools: list[BaseTool] = [
            duckduckgo_search_tool,
            subject_selection_tool,
            subject_context_tool,
        ]
except ImportError as e:
    # Fallback if RAG dependencies are not installed
    print(f"Warning: Could not load RAG tools: {e}")
    tools: list[BaseTool] = [
        duckduckgo_search_tool,
        subject_selection_tool, 
        subject_context_tool,
    ]
