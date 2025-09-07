"""Questions API endpoints for RAG-enhanced content retrieval."""

from typing import Optional
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    Query,
)
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.limiter import limiter
from app.core.logging import logger
from app.models.session import Session
from app.api.v1.auth import get_current_session

# Conditional imports for RAG functionality
try:
    if settings.RAG_ENABLED:
        from app.core.rag.service import get_rag_service
        RAG_AVAILABLE = True
    else:
        RAG_AVAILABLE = False
except ImportError:
    RAG_AVAILABLE = False

router = APIRouter()


class QuestionRequest(BaseModel):
    """Request schema for question asking."""
    
    question: str = Field(description="The question to ask")
    subject_id: Optional[str] = Field(default=None, description="Optional subject ID for filtering")
    language: str = Field(default="en", description="Response language (en, ms, zh)")


class DocumentSearchRequest(BaseModel):
    """Request schema for document search."""
    
    query: str = Field(description="Search query")
    subject_id: Optional[str] = Field(default=None, description="Optional subject ID for filtering")
    top_k: int = Field(default=10, ge=1, le=50, description="Number of results to return")
    score_threshold: float = Field(default=0.7, ge=0.0, le=1.0, description="Minimum similarity score")


class QuestionResponse(BaseModel):
    """Response schema for question answering."""
    
    answer: str = Field(description="Generated answer")
    citations: list[dict] = Field(description="Source citations")
    context_used: int = Field(description="Number of context sources used")
    language: str = Field(description="Response language")
    subject_filter: Optional[str] = Field(description="Applied subject filter")


class DocumentSearchResponse(BaseModel):
    """Response schema for document search."""
    
    results: list[dict] = Field(description="Search results")
    total_results: int = Field(description="Total number of results")
    query: str = Field(description="Original search query")
    subject_filter: Optional[str] = Field(description="Applied subject filter")


class RAGHealthResponse(BaseModel):
    """Response schema for RAG health check."""
    
    status: str = Field(description="Overall RAG system status")
    components: dict = Field(description="Individual component statuses")
    model_info: dict = Field(description="Loaded model information")


@router.post("/ask", response_model=QuestionResponse)
@limiter.limit("20/minute")
async def ask_question(
    request: Request,
    question_request: QuestionRequest,
    session: Session = Depends(get_current_session),
):
    """Ask a question using RAG system.
    
    This endpoint provides comprehensive question answering using the RAG system,
    including document retrieval, answer generation, and citation tracking.
    
    Args:
        request: FastAPI request object for rate limiting
        question_request: Question request with query and options
        session: Current user session
        
    Returns:
        QuestionResponse: Generated answer with citations
        
    Raises:
        HTTPException: If RAG is not enabled or if there's an error
    """
    if not RAG_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="RAG system is not available. Please enable RAG_ENABLED in configuration."
        )
    
    try:
        logger.info(
            "question_request_received",
            session_id=session.id,
            question=question_request.question[:100],
            subject_id=question_request.subject_id,
            language=question_request.language,
        )
        
        # Prepare subject context if provided
        subject_context = None
        
        if question_request.subject_id:
            try:
                from app.services.subject_service import subject_service
                subject = await subject_service.get_subject_by_id(question_request.subject_id)
                if subject:
                    subject_context = {"current_subject": subject.get("name", "")}
                    logger.debug("subject_resolved", subject_id=question_request.subject_id)
            except Exception as e:
                logger.warning("subject_resolution_failed", subject_id=question_request.subject_id, error=str(e))
        
        # Use RAG service for comprehensive answer
        rag_service = get_rag_service()
        result = await rag_service.ask_question(
            query=question_request.question,
            language=question_request.language,
            subject_context=subject_context
        )
        
        if "error" in result:
            raise HTTPException(status_code=500, detail=f"RAG processing failed: {result['error']}")
        
        logger.info(
            "question_answered",
            session_id=session.id,
            citations_count=len(result.get("citations", [])),
            answer_length=len(result.get("answer", "")),
        )
        
        return QuestionResponse(
            answer=result.get("answer", ""),
            citations=result.get("citations", []),
            context_used=result.get("context_used", 0),
            language=result.get("language", question_request.language),
            subject_filter=question_request.subject_id,
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("question_processing_failed", session_id=session.id, error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/search", response_model=DocumentSearchResponse)
@limiter.limit("30/minute")
async def search_documents(
    request: Request,
    search_request: DocumentSearchRequest,
    session: Session = Depends(get_current_session),
):
    """Search for relevant documents in the knowledge base.
    
    This endpoint provides semantic search capabilities to find relevant
    documents based on a query, with optional subject filtering.
    
    Args:
        request: FastAPI request object for rate limiting
        search_request: Search request with query and options
        session: Current user session
        
    Returns:
        DocumentSearchResponse: Search results with metadata
        
    Raises:
        HTTPException: If RAG is not enabled or if there's an error
    """
    if not RAG_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="RAG system is not available. Please enable RAG_ENABLED in configuration."
        )
    
    try:
        logger.info(
            "document_search_request",
            session_id=session.id,
            query=search_request.query[:100],
            subject_id=search_request.subject_id,
            top_k=search_request.top_k,
        )
        
        # Use RAG service for document search
        rag_service = get_rag_service()
        results = await rag_service.search_documents(
            query=search_request.query,
            top_k=search_request.top_k,
            score_threshold=search_request.score_threshold
        )
        
        # Format results for response
        formatted_results = []
        for i, result in enumerate(results):
            formatted_results.append({
                "rank": i + 1,
                "score": round(result["score"], 4),
                "text": result["text"],
                "source": result.get("source", ""),
                "page_num": result.get("page_num"),
                "chapter": result.get("payload", {}).get("chapter", ""),
                "metadata": result.get("payload", {}),
            })
        
        logger.info(
            "document_search_completed",
            session_id=session.id,
            results_count=len(results),
        )
        
        return DocumentSearchResponse(
            results=formatted_results,
            total_results=len(results),
            query=search_request.query,
            subject_filter=search_request.subject_id,
        )
        
    except Exception as e:
        logger.error("document_search_failed", session_id=session.id, error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health", response_model=RAGHealthResponse)
@limiter.limit("10/minute")
async def get_rag_health(request: Request):
    """Get RAG system health status.
    
    This endpoint provides detailed health information about all RAG components,
    including model loading status, vector store connectivity, and configuration.
    
    Args:
        request: FastAPI request object for rate limiting
        
    Returns:
        RAGHealthResponse: Comprehensive health status
    """
    try:
        if not RAG_AVAILABLE:
            return RAGHealthResponse(
                status="disabled",
                components={
                    "rag_enabled": False,
                    "reason": "RAG_ENABLED is False or dependencies not installed"
                },
                model_info={},
            )
        
        # Test individual components
        components = {}
        
        # Test RAG service components
        try:
            rag_service = get_rag_service()
            
            # Test vector store
            vector_store = await rag_service._get_vector_store()
            vector_store_healthy = await vector_store.test_connection()
            components["vector_store"] = {
                "status": "healthy" if vector_store_healthy else "unhealthy",
                "url": settings.QDRANT_URL,
                "collection": settings.QDRANT_COLLECTION,
            }
            
            # Test models
            model_manager = rag_service._get_model_manager()
            model_tests = await model_manager.test_models()
            components["models"] = {
                "embedding": "healthy" if model_tests.get("embedding") else "unhealthy", 
                "llm": "healthy" if model_tests.get("llm") else "unhealthy",
            }
            
            # Test RAG service
            test_result = await rag_service.ask_question("test question")
            service_healthy = "answer" in test_result
            components["rag_service"] = {
                "status": "healthy" if service_healthy else "unhealthy",
            }
            
        except Exception as e:
            components["rag_service"] = {
                "status": "error",
                "error": str(e),
            }
        
        # Get model information
        try:
            rag_service = get_rag_service()
            model_manager = rag_service._get_model_manager()
            model_info = model_manager.get_model_info()
        except Exception as e:
            model_info = {"error": str(e)}
        
        # Determine overall status
        component_statuses = []
        for component in components.values():
            if isinstance(component, dict):
                status = component.get("status", "unknown")
                component_statuses.append(status)
        
        if all(status == "healthy" for status in component_statuses):
            overall_status = "healthy"
        elif any(status == "error" for status in component_statuses):
            overall_status = "error"
        else:
            overall_status = "degraded"
        
        logger.info("rag_health_check", status=overall_status, components=len(components))
        
        return RAGHealthResponse(
            status=overall_status,
            components=components,
            model_info=model_info,
        )
        
    except Exception as e:
        logger.error("rag_health_check_failed", error=str(e), exc_info=True)
        return RAGHealthResponse(
            status="error",
            components={"error": str(e)},
            model_info={},
        )