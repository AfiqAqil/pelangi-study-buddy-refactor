"""Chatwoot webhook endpoints for handling incoming events."""

import asyncio
import json
import time
from typing import Dict, Any

from fastapi import (
    APIRouter,
    Request,
    HTTPException,
    status,
    BackgroundTasks,
)
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.services.agent import agent_service
from app.core.limiter import limiter
from app.core.logging import logger
from app.core.metrics import (
    chatwoot_webhooks_total,
    chatwoot_message_processing_duration_seconds,
    chatwoot_messages_sent_total,
)
from app.schemas.chatwoot import (
    ChatwootMessageWebhook,
    ChatwootConversationWebhook,
    ChatwootEventType,
    MessageMapping,
)
from app.services.chatwoot import chatwoot_service, ChatwootServiceError
from app.services.webhook_queue import webhook_queue_service

router = APIRouter()


@router.post("/webhook")
@limiter.limit(settings.RATE_LIMIT_ENDPOINTS["chatwoot_webhook"][0])
async def chatwoot_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
) -> JSONResponse:
    """Handle incoming Chatwoot webhook events.

    This endpoint receives webhook events from Chatwoot and queues them
    for asynchronous processing. This ensures fast webhook response times
    and better scalability.

    Args:
        request: The FastAPI request object containing the webhook payload
        background_tasks: FastAPI background tasks (kept for compatibility)

    Returns:
        JSONResponse: Acknowledgment response to Chatwoot

    Raises:
        HTTPException: If webhook processing fails
    """
    try:
        # Get the raw webhook payload (check if already read by middleware)
        if hasattr(request.state, "body"):
            body = request.state.body
        else:
            body = await request.body()

        payload = json.loads(body.decode("utf-8"))

        event_type = payload.get("event")
        conversation_id = payload.get("conversation", {}).get("id")

        logger.info(
            "chatwoot_webhook_received",
            event_type=event_type,
            conversation_id=conversation_id,
        )

        # Track webhook metrics
        chatwoot_webhooks_total.labels(event_type=event_type, status="received").inc()

        # Queue webhook for processing based on event type
        if event_type == ChatwootEventType.MESSAGE_CREATED:
            # Parse to validate structure
            webhook_data = ChatwootMessageWebhook(**payload)

            # Only queue incoming messages from customers
            if webhook_data.message_type == "incoming":
                # Add to queue for async processing
                queued = await webhook_queue_service.enqueue(payload)
                
                if queued:
                    logger.debug(
                        "chatwoot_message_queued",
                        message_id=webhook_data.id,
                        conversation_id=conversation_id,
                    )
                else:
                    # Fallback to direct processing if queue fails
                    logger.warning(
                        "chatwoot_queue_failed_using_fallback",
                        message_id=webhook_data.id,
                        conversation_id=conversation_id,
                    )
                    background_tasks.add_task(process_incoming_message, webhook_data)
            else:
                logger.debug(
                    "chatwoot_outgoing_message_ignored", 
                    message_id=webhook_data.id, 
                    conversation_id=conversation_id
                )

        elif event_type == ChatwootEventType.CONVERSATION_CREATED:
            # Parse as conversation webhook
            webhook_data = ChatwootConversationWebhook(**payload)

            logger.debug(
                "chatwoot_conversation_created",
                conversation_id=conversation_id,
                status=webhook_data.conversation.status,
            )

        elif event_type == ChatwootEventType.CONVERSATION_STATUS_CHANGED:
            # Parse as conversation webhook
            webhook_data = ChatwootConversationWebhook(**payload)

            logger.debug(
                "chatwoot_conversation_status_changed",
                conversation_id=conversation_id,
                status=webhook_data.conversation.status,
            )

        elif event_type in [ChatwootEventType.CONVERSATION_TYPING_ON, ChatwootEventType.CONVERSATION_TYPING_OFF]:
            # Log typing events but don't process them
            logger.debug("chatwoot_typing_event", event_type=event_type, conversation_id=conversation_id)

        else:
            logger.debug("chatwoot_unhandled_event", event_type=event_type, conversation_id=conversation_id)

        # Always return 200 to acknowledge receipt
        return JSONResponse(status_code=status.HTTP_200_OK, content={"status": "received", "event": event_type})

    except json.JSONDecodeError as e:
        logger.error("chatwoot_webhook_invalid_json", error=str(e))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON payload")
    except Exception as e:
        logger.error("chatwoot_webhook_processing_error", error=str(e), exc_info=True)
        # Still return 200 to avoid webhook retries for processing errors
        return JSONResponse(
            status_code=status.HTTP_200_OK, content={"status": "error", "message": "Webhook processing failed"}
        )


async def process_incoming_message(webhook_data: ChatwootMessageWebhook) -> None:
    """Process an incoming message from Chatwoot.

    This function handles the core logic of processing messages:
    1. Convert Chatwoot message to internal format
    2. Generate response using LangGraph agent
    3. Send response back to Chatwoot
    4. Handle errors gracefully

    Args:
        webhook_data: The parsed Chatwoot webhook payload
    """
    start_time = time.time()
    processing_status = "failed"

    try:
        # Extract data from the new webhook structure
        message_id = webhook_data.id
        conversation = webhook_data.conversation
        sender = webhook_data.sender
        message_content = webhook_data.content
        message_type = webhook_data.message_type

        logger.info(
            "chatwoot_processing_message",
            message_id=message_id,
            conversation_id=conversation.id,
        )

        # Skip empty messages or system messages
        if not message_content or not message_content.strip():
            logger.debug("chatwoot_empty_message_skipped", message_id=message_id)
            return

        # Convert Chatwoot message to internal format
        internal_message = MessageMapping.chatwoot_to_internal(webhook_data)

        # Generate session ID for conversation persistence
        session_id = MessageMapping.conversation_to_session_id(webhook_data)

        # Generate user ID from sender information
        user_id = f"chatwoot_contact_{sender.id}"

        logger.debug("chatwoot_invoking_agent", session_id=session_id, conversation_id=conversation.id)

        # Get response from LangGraph agent
        agent = agent_service.get_agent()
        response = await agent.get_response(messages=[internal_message], session_id=session_id, user_id=user_id)

        # Send only NEW assistant messages back to Chatwoot (with concurrent processing)
        send_tasks = []
        for agent_msg in response["new_messages"]:
            if agent_msg.role == "assistant" and agent_msg.content:
                # Convert internal message to Chatwoot format
                chatwoot_message = MessageMapping.internal_to_chatwoot(agent_msg)
                # Create concurrent task for sending message
                send_tasks.append(
                    send_message_with_error_handling(conversation.id, chatwoot_message)
                )
        
        # Mark conversation as read concurrently with message sending (fire-and-forget)
        mark_read_task = asyncio.create_task(
            mark_conversation_read_with_error_handling(conversation.id)
        )
        
        # Execute all message sending tasks concurrently for better performance
        if send_tasks:
            await asyncio.gather(*send_tasks, return_exceptions=True)
        
        # Note: mark_read_task runs concurrently and doesn't block response

        logger.debug(
            "chatwoot_message_processing_completed",
            message_id=message_id,
            conversation_id=conversation.id,
        )

        processing_status = "success"

    except Exception as e:
        logger.error(
            "chatwoot_message_processing_error",
            message_id=webhook_data.id,
            conversation_id=webhook_data.conversation.id,
            error=str(e),
            exc_info=True,
        )

        # Optionally send an error message back to Chatwoot
        try:
            from app.schemas.chat import Message

            error_msg = Message(
                role="assistant",
                content="I apologize, but I encountered an error processing your message. Please try again.",
            )
            error_message = MessageMapping.internal_to_chatwoot(error_msg)

            await chatwoot_service.send_message(conversation_id=webhook_data.conversation.id, message=error_message)
        except Exception as send_error:
            logger.error(
                "chatwoot_error_message_send_failed",
                conversation_id=webhook_data.conversation.id,
                error=str(send_error),
            )

    finally:
        # Track processing duration and status
        processing_duration = time.time() - start_time
        chatwoot_message_processing_duration_seconds.labels(status=processing_status).observe(processing_duration)


@router.get("/health")
@limiter.limit("10 per minute")
async def chatwoot_health_check(request: Request) -> Dict[str, Any]:
    """Health check endpoint for Chatwoot integration.

    Args:
        request: The FastAPI request object

    Returns:
        Dict[str, Any]: Health status information
    """
    logger.debug("chatwoot_health_check_called")

    health_info = {
        "status": "healthy",
        "chatwoot_enabled": settings.CHATWOOT_ENABLED,
        "chatwoot_configured": bool(
            settings.CHATWOOT_BASE_URL and settings.CHATWOOT_API_ACCESS_TOKEN and settings.CHATWOOT_ACCOUNT_ID
        ),
    }

    # Test Chatwoot API connectivity if enabled and configured
    if settings.CHATWOOT_ENABLED and health_info["chatwoot_configured"]:
        try:
            chatwoot_healthy = await chatwoot_service.health_check()
            health_info["chatwoot_api_accessible"] = chatwoot_healthy

            if not chatwoot_healthy:
                health_info["status"] = "degraded"

        except Exception as e:
            logger.error("chatwoot_health_check_error", error=str(e))
            health_info["chatwoot_api_accessible"] = False
            health_info["status"] = "degraded"
    else:
        health_info["chatwoot_api_accessible"] = None

    return health_info


@router.get("/config")
@limiter.limit("5 per minute")
async def chatwoot_config(request: Request) -> Dict[str, Any]:
    """Get Chatwoot integration configuration (for debugging).

    Args:
        request: The FastAPI request object

    Returns:
        Dict[str, Any]: Configuration information (sanitized)
    """
    logger.debug("chatwoot_config_requested")

    return {
        "enabled": settings.CHATWOOT_ENABLED,
        "base_url": settings.CHATWOOT_BASE_URL,
        "account_id": settings.CHATWOOT_ACCOUNT_ID,
        "has_api_token": bool(settings.CHATWOOT_API_ACCESS_TOKEN),
        "timeout": settings.CHATWOOT_TIMEOUT,
        "max_retries": settings.CHATWOOT_MAX_RETRIES,
    }


@router.get("/queue/stats")
@limiter.limit("10 per minute")
async def chatwoot_queue_stats(request: Request) -> Dict[str, Any]:
    """Get webhook queue statistics.

    Args:
        request: The FastAPI request object

    Returns:
        Dict[str, Any]: Queue statistics
    """
    from app.workers.webhook_worker import webhook_worker_pool
    from app.core.circuit_breaker import circuit_breaker_manager
    
    logger.debug("chatwoot_queue_stats_requested")
    
    # Get queue statistics
    queue_size = await webhook_queue_service.get_queue_size()
    processing_count = await webhook_queue_service.get_processing_count()
    
    # Get worker pool stats if available
    worker_stats = {}
    if webhook_worker_pool:
        worker_stats = await webhook_worker_pool.get_stats()
    
    # Get circuit breaker stats
    circuit_stats = circuit_breaker_manager.get_all_stats().get("chatwoot_api", {})
    
    return {
        "queue": {
            "size": queue_size,
            "processing": processing_count,
        },
        "workers": worker_stats,
        "circuit_breaker": circuit_stats,
    }


# Helper functions for concurrent API operations
async def send_message_with_error_handling(conversation_id: int, chatwoot_message) -> None:
    """Send message to Chatwoot with proper error handling for concurrent execution."""
    try:
        response_msg = await chatwoot_service.send_message(
            conversation_id=conversation_id, message=chatwoot_message
        )
        
        # Track successful message sending
        chatwoot_messages_sent_total.labels(status="success").inc()
        
        logger.debug(
            "chatwoot_message_sent",
            conversation_id=conversation_id,
            message_id=response_msg.id,
        )
        
    except ChatwootServiceError as e:
        # Track failed message sending
        chatwoot_messages_sent_total.labels(status="failed").inc()
        logger.error("chatwoot_send_message_failed", conversation_id=conversation_id, error=str(e))
    except Exception as e:
        logger.error("chatwoot_send_message_unexpected_error", conversation_id=conversation_id, error=str(e))


async def mark_conversation_read_with_error_handling(conversation_id: int) -> None:
    """Mark conversation as read with proper error handling for concurrent execution."""
    try:
        await chatwoot_service.mark_conversation_as_read(conversation_id)
    except ChatwootServiceError as e:
        logger.warning("chatwoot_mark_read_failed", conversation_id=conversation_id, error=str(e))
    except Exception as e:
        logger.error("chatwoot_mark_read_unexpected_error", conversation_id=conversation_id, error=str(e))


