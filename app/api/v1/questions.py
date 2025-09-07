"""Questions API endpoints for RAG-enhanced content retrieval and quiz system."""

from typing import Optional, Dict, Any
from datetime import datetime
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    Query,
    Path,
)
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.limiter import limiter
from app.core.logging import logger
from app.models.session import Session
from app.api.v1.auth import get_current_session
from app.services.question_service import question_service

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


# Quiz System Schemas
class QuizQuestionRequest(BaseModel):
    """Request schema for getting a quiz question."""
    
    subject: Optional[str] = Field(default=None, description="Subject filter (e.g., 'math', 'science')")
    difficulty_level: Optional[str] = Field(default=None, description="Difficulty level ('easy', 'moderate', 'hard')")
    form_level: Optional[int] = Field(default=None, ge=1, le=5, description="Form level (1-5)")
    question_type: Optional[str] = Field(default=None, description="Question type filter")
    language: str = Field(default="english", description="Question language ('english', 'malay', 'chinese')")
    exclude_attempted: bool = Field(default=True, description="Exclude previously attempted questions")
    adaptive_difficulty: bool = Field(default=True, description="Use adaptive difficulty based on performance")


class QuizStartRequest(BaseModel):
    """Request schema for starting a quiz session."""
    
    subject: Optional[str] = Field(default=None, description="Subject filter")
    difficulty_level: Optional[str] = Field(default=None, description="Fixed difficulty level")
    form_level: Optional[int] = Field(default=None, ge=1, le=5, description="Form level filter")
    question_count: int = Field(default=10, ge=1, le=50, description="Number of questions in quiz")
    language: str = Field(default="english", description="Quiz language")
    adaptive_difficulty: bool = Field(default=True, description="Enable adaptive difficulty")


class QuizGradeRequest(BaseModel):
    """Request schema for grading a quiz answer."""
    
    question_id: str = Field(description="Question ID being answered")
    user_answer: str = Field(description="User's answer")
    time_taken_seconds: Optional[int] = Field(default=None, description="Time taken to answer")
    session_id: Optional[str] = Field(default=None, description="Quiz session ID")


class QuizQuestionResponse(BaseModel):
    """Response schema for quiz questions."""
    
    id: str = Field(description="Question ID")
    question: str = Field(description="Question text")
    subject: str = Field(description="Question subject")
    difficulty_level: str = Field(description="Difficulty level")
    forms: Optional[list[int]] = Field(description="Applicable form levels")
    language: str = Field(description="Question language")
    question_type: Optional[str] = Field(description="Question type")
    blooms_level: Optional[str] = Field(description="Bloom's taxonomy level")
    blooms_descriptor: Optional[str] = Field(description="Bloom's taxonomy descriptor")
    learning_standards: Optional[list[str]] = Field(description="Learning standards covered")
    chapter_number: Optional[str] = Field(description="Chapter number")
    chapter_name: Optional[str] = Field(description="Chapter name")
    source: Optional[str] = Field(description="Question source")
    requires_latex: Optional[bool] = Field(description="Whether LaTeX rendering is needed")
    contains_calculations: Optional[bool] = Field(description="Whether calculations are involved")
    knowledge_snippet: Optional[str] = Field(description="Context knowledge snippet")
    knowledge_snippet_type: Optional[str] = Field(description="Type of knowledge snippet")
    question_image_uri: Optional[str] = Field(description="Question-associated image URI")
    answer_image_uri: Optional[str] = Field(description="Answer-associated image URI")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class QuizGradeResponse(BaseModel):
    """Response schema for quiz grading."""
    
    question_id: str = Field(description="Question ID")
    user_answer: str = Field(description="User's submitted answer")
    is_correct: bool = Field(description="Whether the answer is correct")
    correct_answer: str = Field(description="The correct answer")
    score: float = Field(description="Score percentage (0.0 - 1.0)")
    feedback: str = Field(description="Detailed feedback on the answer")
    explanation: Optional[str] = Field(description="Explanation of the correct answer")
    grading_method: str = Field(description="Method used for grading")
    time_taken_seconds: Optional[int] = Field(description="Time taken to answer")
    attempt_recorded: bool = Field(description="Whether attempt was saved to database")


class QuizHistoryResponse(BaseModel):
    """Response schema for quiz history."""
    
    attempts: list[Dict[str, Any]] = Field(description="List of quiz attempts")
    metrics: Dict[str, Any] = Field(description="Performance metrics")
    total_attempts: int = Field(description="Total number of attempts")
    subject_filter: Optional[str] = Field(description="Applied subject filter")


class QuizSessionResponse(BaseModel):
    """Response schema for quiz session start."""
    
    session_id: str = Field(description="Quiz session identifier")
    configuration: Dict[str, Any] = Field(description="Quiz configuration")
    first_question: Optional[QuizQuestionResponse] = Field(description="First question in the quiz")
    total_questions: int = Field(description="Total questions planned")
    adaptive_enabled: bool = Field(description="Whether adaptive difficulty is enabled")


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


# Quiz System Endpoints
@router.get("/quiz/random", response_model=QuizQuestionResponse)
@limiter.limit("30/minute")
async def get_random_quiz_question(
    request: Request,
    session: Session = Depends(get_current_session),
    subject: Optional[str] = Query(default=None, description="Subject filter"),
    difficulty_level: Optional[str] = Query(default=None, description="Difficulty level"),
    form_level: Optional[int] = Query(default=None, ge=1, le=5, description="Form level"),
    question_type: Optional[str] = Query(default=None, description="Question type filter"),
    language: str = Query(default="english", description="Question language"),
    exclude_attempted: bool = Query(default=True, description="Exclude attempted questions"),
    adaptive_difficulty: bool = Query(default=True, description="Use adaptive difficulty")
):
    """Get a random quiz question based on criteria and user progress.
    
    This endpoint provides intelligent question selection using filtering criteria
    and adaptive difficulty based on user performance history.
    
    Args:
        request: FastAPI request object for rate limiting
        session: Current user session
        subject: Optional subject filter
        difficulty_level: Optional difficulty level filter
        form_level: Optional form level filter (1-5)
        question_type: Optional question type filter
        language: Question language preference
        exclude_attempted: Whether to exclude previously attempted questions
        adaptive_difficulty: Whether to use adaptive difficulty progression
        
    Returns:
        QuizQuestionResponse: Random quiz question with metadata
        
    Raises:
        HTTPException: If no questions found or error occurs
    """
    try:
        logger.info(
            "random_quiz_question_requested",
            user_id=session.user_id,
            subject=subject,
            difficulty=difficulty_level,
            form_level=form_level,
            language=language
        )
        
        question_data = await question_service.get_random_question(
            user_id=session.user_id,
            subject=subject,
            difficulty_level=difficulty_level,
            form_level=form_level,
            question_type=question_type,
            language=language,
            exclude_attempted=exclude_attempted,
            adaptive_difficulty=adaptive_difficulty
        )
        
        if not question_data:
            raise HTTPException(
                status_code=404,
                detail="No questions found matching the specified criteria"
            )
        
        # Convert to response model
        response = QuizQuestionResponse(**question_data)
        
        logger.info(
            "random_quiz_question_served",
            user_id=session.user_id,
            question_id=question_data["id"],
            subject=question_data["subject"],
            difficulty=question_data["difficulty_level"]
        )
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "random_quiz_question_failed",
            user_id=session.user_id,
            error=str(e),
            exc_info=True
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/quiz/start", response_model=QuizSessionResponse)
@limiter.limit("10/minute")
async def start_quiz_session(
    request: Request,
    quiz_request: QuizStartRequest,
    session: Session = Depends(get_current_session)
):
    """Start a new quiz session with specified configuration.
    
    This endpoint initializes a quiz session and provides the first question.
    The session configuration determines question selection criteria.
    
    Args:
        request: FastAPI request object for rate limiting
        quiz_request: Quiz configuration request
        session: Current user session
        
    Returns:
        QuizSessionResponse: Quiz session details and first question
        
    Raises:
        HTTPException: If unable to start quiz session
    """
    try:
        import uuid
        
        # Generate quiz session ID
        quiz_session_id = str(uuid.uuid4())
        
        logger.info(
            "quiz_session_start_requested",
            user_id=session.user_id,
            quiz_session_id=quiz_session_id,
            config=quiz_request.dict()
        )
        
        # Get first question
        first_question = await question_service.get_random_question(
            user_id=session.user_id,
            subject=quiz_request.subject,
            difficulty_level=quiz_request.difficulty_level,
            form_level=quiz_request.form_level,
            language=quiz_request.language,
            exclude_attempted=True,
            adaptive_difficulty=quiz_request.adaptive_difficulty
        )
        
        if not first_question:
            raise HTTPException(
                status_code=404,
                detail="Unable to find questions for quiz session"
            )
        
        # Store quiz configuration in session cache if needed
        configuration = {
            "subject": quiz_request.subject,
            "difficulty_level": quiz_request.difficulty_level,
            "form_level": quiz_request.form_level,
            "question_count": quiz_request.question_count,
            "language": quiz_request.language,
            "adaptive_difficulty": quiz_request.adaptive_difficulty,
            "created_at": datetime.utcnow().isoformat()
        }
        
        response = QuizSessionResponse(
            session_id=quiz_session_id,
            configuration=configuration,
            first_question=QuizQuestionResponse(**first_question),
            total_questions=quiz_request.question_count,
            adaptive_enabled=quiz_request.adaptive_difficulty
        )
        
        logger.info(
            "quiz_session_started",
            user_id=session.user_id,
            quiz_session_id=quiz_session_id,
            first_question_id=first_question["id"]
        )
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "quiz_session_start_failed",
            user_id=session.user_id,
            error=str(e),
            exc_info=True
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/quiz/grade", response_model=QuizGradeResponse)
@limiter.limit("50/minute")
async def grade_quiz_answer(
    request: Request,
    grade_request: QuizGradeRequest,
    session: Session = Depends(get_current_session)
):
    """Grade a quiz answer and provide feedback.
    
    This endpoint evaluates user answers using multiple grading methods
    including exact matching and LLM-based semantic evaluation.
    
    Args:
        request: FastAPI request object for rate limiting
        grade_request: Answer grading request
        session: Current user session
        
    Returns:
        QuizGradeResponse: Grading results with feedback
        
    Raises:
        HTTPException: If question not found or grading fails
    """
    try:
        from datetime import datetime
        
        logger.info(
            "quiz_answer_grading_requested",
            user_id=session.user_id,
            question_id=grade_request.question_id,
            answer_length=len(grade_request.user_answer)
        )
        
        # Get the question with correct answer
        question_data = await question_service.get_question_by_id(grade_request.question_id)
        
        if not question_data:
            raise HTTPException(
                status_code=404,
                detail="Question not found"
            )
        
        # Import grading tools (will be implemented next)
        try:
            from app.core.langgraph.tools.quiz_tools import grade_quiz_answer_tool
            
            # Use LLM-based grading tool
            grading_result = await grade_quiz_answer_tool.ainvoke({
                "question": question_data["question"],
                "correct_answer": question_data["answer"],
                "user_answer": grade_request.user_answer,
                "question_type": question_data.get("question_type"),
                "language": question_data.get("language", "english"),
                "subject": question_data.get("subject"),
                "requires_calculations": question_data.get("contains_calculations", False),
                "question_image_uri": question_data.get("question_image_uri"),
                "answer_image_uri": question_data.get("answer_image_uri")
            })
            
            is_correct = grading_result.get("is_correct", False)
            score = grading_result.get("score", 0.0)
            feedback = grading_result.get("feedback", "Answer evaluated.")
            explanation = grading_result.get("explanation")
            grading_method = grading_result.get("method", "llm_based")
            
        except ImportError:
            # Fallback to simple string matching if LLM grading not available
            logger.warning("LLM grading tools not available, using simple matching")
            
            correct_answer = question_data["answer"].strip().lower()
            user_answer = grade_request.user_answer.strip().lower()
            
            is_correct = correct_answer == user_answer
            score = 1.0 if is_correct else 0.0
            feedback = "Correct!" if is_correct else f"Incorrect. The correct answer is: {question_data['answer']}"
            explanation = None
            grading_method = "exact_match"
        
        # Record the attempt in database
        session_id = grade_request.session_id or session.id
        attempt_recorded = await question_service.record_quiz_attempt(
            user_id=session.user_id,
            question_id=grade_request.question_id,
            session_id=session_id,
            user_answer=grade_request.user_answer,
            is_correct=is_correct,
            time_taken_seconds=grade_request.time_taken_seconds
        )
        
        response = QuizGradeResponse(
            question_id=grade_request.question_id,
            user_answer=grade_request.user_answer,
            is_correct=is_correct,
            correct_answer=question_data["answer"],
            score=score,
            feedback=feedback,
            explanation=explanation,
            grading_method=grading_method,
            time_taken_seconds=grade_request.time_taken_seconds,
            attempt_recorded=attempt_recorded
        )
        
        logger.info(
            "quiz_answer_graded",
            user_id=session.user_id,
            question_id=grade_request.question_id,
            is_correct=is_correct,
            score=score,
            method=grading_method
        )
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "quiz_answer_grading_failed",
            user_id=session.user_id,
            question_id=grade_request.question_id,
            error=str(e),
            exc_info=True
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/users/{user_id}/quiz/history", response_model=QuizHistoryResponse)
@limiter.limit("20/minute")
async def get_user_quiz_history(
    request: Request,
    user_id: str = Path(description="User ID to get history for"),
    session: Session = Depends(get_current_session),
    subject: Optional[str] = Query(default=None, description="Subject filter"),
    limit: int = Query(default=50, ge=1, le=200, description="Maximum results"),
    offset: int = Query(default=0, ge=0, description="Results offset")
):
    """Get user's quiz attempt history with performance metrics.
    
    This endpoint provides comprehensive quiz history including performance
    analytics, streak information, and subject-specific metrics.
    
    Args:
        request: FastAPI request object for rate limiting
        user_id: User ID to retrieve history for
        session: Current user session
        subject: Optional subject filter
        limit: Maximum number of attempts to return
        offset: Number of attempts to skip
        
    Returns:
        QuizHistoryResponse: Quiz history and performance metrics
        
    Raises:
        HTTPException: If user not authorized or error occurs
    """
    try:
        # Check if user can access this history (own history or admin access)
        if session.user_id != user_id:
            # For now, users can only access their own history
            # In future, add admin role check here
            raise HTTPException(
                status_code=403,
                detail="Not authorized to access this user's quiz history"
            )
        
        logger.info(
            "quiz_history_requested",
            requesting_user_id=session.user_id,
            target_user_id=user_id,
            subject=subject,
            limit=limit,
            offset=offset
        )
        
        history_data = await question_service.get_user_quiz_history(
            user_id=user_id,
            subject=subject,
            limit=limit,
            offset=offset
        )
        
        response = QuizHistoryResponse(**history_data)
        
        logger.info(
            "quiz_history_retrieved",
            user_id=user_id,
            attempts_count=len(history_data["attempts"]),
            subject_filter=subject
        )
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "quiz_history_retrieval_failed",
            user_id=user_id,
            error=str(e),
            exc_info=True
        )
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