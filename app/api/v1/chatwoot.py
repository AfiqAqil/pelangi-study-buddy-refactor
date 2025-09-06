"""Chatwoot webhook endpoints for handling incoming events."""

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
from app.core.langgraph.graph import LangGraphAgent
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

router = APIRouter()
agent = LangGraphAgent()


@router.post("/webhook")
@limiter.limit(settings.RATE_LIMIT_ENDPOINTS["chatwoot_webhook"][0])
async def chatwoot_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
) -> JSONResponse:
    """Handle incoming Chatwoot webhook events.

    This endpoint receives webhook events from Chatwoot and processes them
    based on the event type. Message events are processed asynchronously
    to avoid blocking the webhook response.

    Args:
        request: The FastAPI request object containing the webhook payload
        background_tasks: FastAPI background tasks for async processing

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
            account_id=payload.get("account", {}).get("id"),
            inbox_id=payload.get("inbox", {}).get("id"),
        )

        # Debug: Log the full payload structure
        logger.debug(
            "chatwoot_webhook_full_payload",
            event_type=event_type,
            payload_keys=list(payload.keys()),
            conversation_keys=list(payload.get("conversation", {}).keys()) if "conversation" in payload else [],
            message_keys=list(payload.get("message", {}).keys()) if "message" in payload else [],
            contact_keys=list(payload.get("contact", {}).keys()) if "contact" in payload else [],
        )

        # Track webhook metrics
        chatwoot_webhooks_total.labels(event_type=event_type, status="received").inc()

        # Handle different event types
        if event_type == ChatwootEventType.MESSAGE_CREATED:
            # Parse as message webhook
            webhook_data = ChatwootMessageWebhook(**payload)

            # Only process incoming messages from customers (not agent messages)
            if webhook_data.message_type == "incoming":
                # Process message asynchronously to avoid blocking webhook response
                background_tasks.add_task(process_incoming_message, webhook_data)

                logger.info(
                    "chatwoot_message_queued_for_processing",
                    message_id=webhook_data.id,
                    conversation_id=conversation_id,
                )
            else:
                logger.info(
                    "chatwoot_outgoing_message_ignored", message_id=webhook_data.id, conversation_id=conversation_id
                )

        elif event_type == ChatwootEventType.CONVERSATION_CREATED:
            # Parse as conversation webhook
            webhook_data = ChatwootConversationWebhook(**payload)

            logger.info(
                "chatwoot_conversation_created",
                conversation_id=conversation_id,
                status=webhook_data.conversation.status,
            )

        elif event_type == ChatwootEventType.CONVERSATION_STATUS_CHANGED:
            # Parse as conversation webhook
            webhook_data = ChatwootConversationWebhook(**payload)

            logger.info(
                "chatwoot_conversation_status_changed",
                conversation_id=conversation_id,
                status=webhook_data.conversation.status,
                changed_attributes=webhook_data.changed_attributes,
            )

        elif event_type in [ChatwootEventType.CONVERSATION_TYPING_ON, ChatwootEventType.CONVERSATION_TYPING_OFF]:
            # Log typing events but don't process them
            logger.info("chatwoot_typing_event", event_type=event_type, conversation_id=conversation_id)

        else:
            logger.info("chatwoot_unhandled_event", event_type=event_type, conversation_id=conversation_id)

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
            contact_id=sender.id,
            content_preview=message_content[:100],
            message_type=message_type,
            sender_name=sender.name,
        )

        # Skip empty messages or system messages
        if not message_content or not message_content.strip():
            logger.info("chatwoot_empty_message_skipped", message_id=message_id)
            return

        # Convert Chatwoot message to internal format
        internal_message = MessageMapping.chatwoot_to_internal(webhook_data)

        # Generate session ID for conversation persistence
        session_id = MessageMapping.conversation_to_session_id(webhook_data)

        # Generate user ID from sender information
        user_id = f"chatwoot_contact_{sender.id}"

        logger.info("chatwoot_invoking_agent", session_id=session_id, user_id=user_id, conversation_id=conversation.id)

        # Get response from LangGraph agent
        response = await agent.get_response(messages=[internal_message], session_id=session_id, user_id=user_id)

        # Send only NEW assistant messages back to Chatwoot
        for agent_msg in response["new_messages"]:
            if agent_msg.role == "assistant" and agent_msg.content:
                try:
                    # Convert internal message to Chatwoot format
                    chatwoot_message = MessageMapping.internal_to_chatwoot(agent_msg)

                    # Send message to Chatwoot
                    response_msg = await chatwoot_service.send_message(
                        conversation_id=conversation.id, message=chatwoot_message
                    )

                    # Track successful message sending
                    chatwoot_messages_sent_total.labels(status="success").inc()

                    logger.info(
                        "chatwoot_message_sent",
                        conversation_id=conversation.id,
                        message_id=response_msg.id,
                        content_preview=agent_msg.content[:100],
                    )

                except ChatwootServiceError as e:
                    # Track failed message sending
                    chatwoot_messages_sent_total.labels(status="failed").inc()

                    logger.error("chatwoot_send_message_failed", conversation_id=conversation.id, error=str(e))
                    # Continue processing other messages even if one fails
                    continue

        # Mark conversation as read by the agent
        try:
            await chatwoot_service.mark_conversation_as_read(conversation.id)
        except ChatwootServiceError as e:
            logger.warning("chatwoot_mark_read_failed", conversation_id=conversation.id, error=str(e))
            # Non-critical error, continue

        logger.info(
            "chatwoot_message_processing_completed",
            message_id=message_id,
            conversation_id=conversation.id,
            responses_sent=len([msg for msg in response["new_messages"] if msg.role == "assistant"]),
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
    logger.info("chatwoot_health_check_called")

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
    logger.info("chatwoot_config_requested")

    return {
        "enabled": settings.CHATWOOT_ENABLED,
        "base_url": settings.CHATWOOT_BASE_URL,
        "account_id": settings.CHATWOOT_ACCOUNT_ID,
        "has_api_token": bool(settings.CHATWOOT_API_ACCESS_TOKEN),
        "timeout": settings.CHATWOOT_TIMEOUT,
        "max_retries": settings.CHATWOOT_MAX_RETRIES,
    }
