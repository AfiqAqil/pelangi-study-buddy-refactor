"""Chatbot API endpoints for handling chat interactions.

This module provides endpoints for chat interactions, including regular chat,
streaming chat, message history management, and chat history clearing.
"""

import json

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    Query,
)
from fastapi.responses import StreamingResponse
from app.core.metrics import llm_stream_duration_seconds
from app.api.v1.auth import get_current_session
from app.core.config import settings
from app.services.agent import agent_service
from app.services.quota_service import quota_service
from app.core.limiter import limiter
from app.core.logging import logger
from app.models.session import Session
from app.schemas.chat import (
    ChatRequest,
    ChatResponse,
    StreamResponse,
)
from app.schemas.quota import (
    QuotaStatusResponse,
    QuotaHistoryResponse,
)

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
@limiter.limit(settings.RATE_LIMIT_ENDPOINTS["chat"][0])
async def chat(
    request: Request,
    chat_request: ChatRequest,
    session: Session = Depends(get_current_session),
):
    """Process a chat request using LangGraph.

    Args:
        request: The FastAPI request object for rate limiting.
        chat_request: The chat request containing messages.
        session: The current session from the auth token.

    Returns:
        ChatResponse: The processed chat response.

    Raises:
        HTTPException: If there's an error processing the request.
    """
    try:
        logger.info(
            "chat_request_received",
            session_id=session.id,
            message_count=len(chat_request.messages),
        )

        agent = agent_service.get_agent()
        result = await agent.get_response(chat_request.messages, session.id, user_id=session.user_id)

        logger.info("chat_request_processed", session_id=session.id)

        return ChatResponse(messages=result["messages"])
    except Exception as e:
        logger.error("chat_request_failed", session_id=session.id, error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat/stream")
@limiter.limit(settings.RATE_LIMIT_ENDPOINTS["chat_stream"][0])
async def chat_stream(
    request: Request,
    chat_request: ChatRequest,
    session: Session = Depends(get_current_session),
):
    """Process a chat request using LangGraph with streaming response.

    Args:
        request: The FastAPI request object for rate limiting.
        chat_request: The chat request containing messages.
        session: The current session from the auth token.

    Returns:
        StreamingResponse: A streaming response of the chat completion.

    Raises:
        HTTPException: If there's an error processing the request.
    """
    try:
        logger.info(
            "stream_chat_request_received",
            session_id=session.id,
            message_count=len(chat_request.messages),
        )

        async def event_generator():
            """Generate streaming events.

            Yields:
                str: Server-sent events in JSON format.

            Raises:
                Exception: If there's an error during streaming.
            """
            try:
                agent = agent_service.get_agent()
                full_response = ""
                # Use the centralized method to get model name
                model_name = agent.get_model_name()
                with llm_stream_duration_seconds.labels(model=model_name).time():
                    async for chunk in agent.get_stream_response(
                        chat_request.messages, session.id, user_id=session.user_id
                    ):
                        full_response += chunk
                        response = StreamResponse(content=chunk, done=False)
                        yield f"data: {json.dumps(response.model_dump())}\n\n"

                # Send final message indicating completion
                final_response = StreamResponse(content="", done=True)
                yield f"data: {json.dumps(final_response.model_dump())}\n\n"

            except Exception as e:
                logger.error(
                    "stream_chat_request_failed",
                    session_id=session.id,
                    error=str(e),
                    exc_info=True,
                )
                error_response = StreamResponse(content=str(e), done=True)
                yield f"data: {json.dumps(error_response.model_dump())}\n\n"

        return StreamingResponse(event_generator(), media_type="text/event-stream")

    except Exception as e:
        logger.error(
            "stream_chat_request_failed",
            session_id=session.id,
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/messages", response_model=ChatResponse)
@limiter.limit(settings.RATE_LIMIT_ENDPOINTS["messages"][0])
async def get_session_messages(
    request: Request,
    session: Session = Depends(get_current_session),
):
    """Get all messages for a session.

    Args:
        request: The FastAPI request object for rate limiting.
        session: The current session from the auth token.

    Returns:
        ChatResponse: All messages in the session.

    Raises:
        HTTPException: If there's an error retrieving the messages.
    """
    try:
        agent = agent_service.get_agent()
        messages = await agent.get_chat_history(session.id)
        return ChatResponse(messages=messages)
    except Exception as e:
        logger.error("get_messages_failed", session_id=session.id, error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/messages")
@limiter.limit(settings.RATE_LIMIT_ENDPOINTS["messages"][0])
async def clear_chat_history(
    request: Request,
    session: Session = Depends(get_current_session),
):
    """Clear all messages for a session.

    Args:
        request: The FastAPI request object for rate limiting.
        session: The current session from the auth token.

    Returns:
        dict: A message indicating the chat history was cleared.
    """
    try:
        agent = agent_service.get_agent()
        await agent.clear_chat_history(session.id)
        return {"message": "Chat history cleared successfully"}
    except Exception as e:
        logger.error("clear_chat_history_failed", session_id=session.id, error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/quota/status", response_model=QuotaStatusResponse)
@limiter.limit("30/minute")
async def get_quota_status(
    request: Request,
    session: Session = Depends(get_current_session),
):
    """Get user's current quota status for both quiz and message quotas.

    Args:
        request: The FastAPI request object for rate limiting
        session: The current session from the auth token

    Returns:
        QuotaStatusResponse: Current quota status with limits and usage
    """
    try:
        user_id = session.user_id

        quota_status = await quota_service.get_quota_status(user_id)
        if not quota_status:
            raise HTTPException(status_code=500, detail="Failed to retrieve quota status")

        logger.info("quota_status_retrieved", user_id=user_id, tier=quota_status.tier)

        return QuotaStatusResponse(
            quiz_quota=quota_status.quiz_quota.__dict__,
            message_quota=quota_status.message_quota.__dict__,
            tier=quota_status.tier,
            upgrade_available=quota_status.upgrade_available,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("error_getting_quota_status", error=str(e), user_id=session.user_id)
        raise HTTPException(status_code=500, detail="Failed to retrieve quota status")


@router.get("/quota/history", response_model=QuotaHistoryResponse)
@limiter.limit("20/minute")
async def get_quota_history(
    request: Request,
    session: Session = Depends(get_current_session),
    days: int = Query(7, ge=1, le=30, description="Number of days to retrieve (1-30)"),
):
    """Get user's quota usage history.

    Args:
        request: The FastAPI request object for rate limiting
        session: The current session from the auth token
        days: Number of days to retrieve history for

    Returns:
        QuotaHistoryResponse: Quota usage history
    """
    try:
        user_id = session.user_id

        history = await quota_service.get_quota_history(user_id, days)

        # Calculate totals
        total_quiz_attempted = sum(day["quiz_attempted"] for day in history)
        total_messages_sent = sum(day["messages_sent"] for day in history)

        logger.info(
            "quota_history_retrieved",
            user_id=user_id,
            days=days,
            total_quiz=total_quiz_attempted,
            total_messages=total_messages_sent,
        )

        return QuotaHistoryResponse(
            history=history,
            days=len(history),
            total_quiz_attempted=total_quiz_attempted,
            total_messages_sent=total_messages_sent,
        )

    except Exception as e:
        logger.error("error_getting_quota_history", error=str(e), user_id=session.user_id)
        raise HTTPException(status_code=500, detail="Failed to retrieve quota history")
