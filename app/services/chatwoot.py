"""Chatwoot API service for sending messages and managing conversations."""

import asyncio
import time
from typing import Dict, List, Optional, Any
from datetime import datetime

import aiohttp
from aiohttp import ClientTimeout, ClientError

from app.core.config import settings
from app.core.logging import logger
from app.core.metrics import (
    chatwoot_api_requests_total,
    chatwoot_api_request_duration_seconds,
)
from app.schemas.chatwoot import (
    ChatwootApiMessage,
    ChatwootApiResponse,
    ChatwootConversation,
    ChatwootContact,
    ChatwootMessage,
)


class ChatwootServiceError(Exception):
    """Exception raised for Chatwoot service errors."""

    pass


class ChatwootService:
    """Service for interacting with the Chatwoot API."""

    def __init__(self):
        """Initialize the Chatwoot service with configuration."""
        self.base_url = settings.CHATWOOT_BASE_URL.rstrip("/")
        self.api_access_token = settings.CHATWOOT_API_ACCESS_TOKEN
        self.account_id = settings.CHATWOOT_ACCOUNT_ID
        self.timeout = ClientTimeout(total=settings.CHATWOOT_TIMEOUT)
        self.max_retries = settings.CHATWOOT_MAX_RETRIES

        # Validate configuration
        if not all([self.base_url, self.api_access_token, self.account_id]):
            logger.warning(
                "chatwoot_service_incomplete_config",
                base_url=bool(self.base_url),
                api_token=bool(self.api_access_token),
                account_id=bool(self.account_id),
            )

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Make an HTTP request to the Chatwoot API with retry logic.

        Args:
            method: HTTP method (GET, POST, PATCH, etc.)
            endpoint: API endpoint path
            data: Request payload for POST/PATCH requests
            params: Query parameters

        Returns:
            Dict[str, Any]: Response data from the API

        Raises:
            ChatwootServiceError: If the API request fails after retries
        """
        url = f"{self.base_url}/api/v1/accounts/{self.account_id}/{endpoint}"
        headers = {
            "api_access_token": self.api_access_token,
            "Content-Type": "application/json",
        }

        # Track request start time for metrics
        request_start_time = time.time()

        for attempt in range(self.max_retries):
            try:
                async with aiohttp.ClientSession(timeout=self.timeout) as session:
                    async with session.request(
                        method=method, url=url, json=data, params=params, headers=headers
                    ) as response:
                        response_data = await response.json()

                        if response.status == 200 or response.status == 201:
                            # Track successful API request metrics
                            duration = time.time() - request_start_time
                            chatwoot_api_requests_total.labels(
                                endpoint=endpoint, method=method, status="success"
                            ).inc()
                            chatwoot_api_request_duration_seconds.labels(endpoint=endpoint, method=method).observe(
                                duration
                            )

                            logger.info(
                                "chatwoot_api_success",
                                method=method,
                                endpoint=endpoint,
                                status=response.status,
                                attempt=attempt + 1,
                                duration=duration,
                            )
                            return response_data
                        else:
                            logger.warning(
                                "chatwoot_api_error",
                                method=method,
                                endpoint=endpoint,
                                status=response.status,
                                response=response_data,
                                attempt=attempt + 1,
                            )

                            # Don't retry for client errors (4xx)
                            if 400 <= response.status < 500:
                                raise ChatwootServiceError(
                                    f"Chatwoot API client error: {response.status} - {response_data}"
                                )

            except ClientError as e:
                logger.error(
                    "chatwoot_api_client_error", method=method, endpoint=endpoint, error=str(e), attempt=attempt + 1
                )

                # If this is the last attempt, raise the error
                if attempt == self.max_retries - 1:
                    raise ChatwootServiceError(f"Chatwoot API request failed: {str(e)}")

                # Wait before retrying (exponential backoff)
                await asyncio.sleep(2**attempt)

            except Exception as e:
                logger.error(
                    "chatwoot_api_unexpected_error",
                    method=method,
                    endpoint=endpoint,
                    error=str(e),
                    attempt=attempt + 1,
                )

                if attempt == self.max_retries - 1:
                    raise ChatwootServiceError(f"Unexpected error in Chatwoot API: {str(e)}")

                await asyncio.sleep(2**attempt)

        # Track failed API request (if we reach this point, all retries failed)
        chatwoot_api_requests_total.labels(endpoint=endpoint, method=method, status="failed").inc()

        raise ChatwootServiceError("Max retries exceeded for Chatwoot API request")

    async def send_message(self, conversation_id: int, message: ChatwootApiMessage) -> ChatwootApiResponse:
        """Send a message to a Chatwoot conversation.

        Args:
            conversation_id: The Chatwoot conversation ID
            message: The message to send

        Returns:
            ChatwootApiResponse: The API response

        Raises:
            ChatwootServiceError: If sending the message fails
        """
        try:
            endpoint = f"conversations/{conversation_id}/messages"
            data = message.model_dump()

            logger.info(
                "chatwoot_sending_message",
                conversation_id=conversation_id,
                message_type=message.message_type,
                content_preview=message.content[:100],
            )

            response_data = await self._make_request("POST", endpoint, data)

            return ChatwootApiResponse(id=response_data.get("id"), message="Message sent successfully")

        except Exception as e:
            logger.error("chatwoot_send_message_failed", conversation_id=conversation_id, error=str(e))
            raise ChatwootServiceError(f"Failed to send message: {str(e)}")

    async def get_conversation(self, conversation_id: int) -> Optional[ChatwootConversation]:
        """Get conversation details from Chatwoot.

        Args:
            conversation_id: The Chatwoot conversation ID

        Returns:
            Optional[ChatwootConversation]: The conversation details or None if not found

        Raises:
            ChatwootServiceError: If fetching the conversation fails
        """
        try:
            endpoint = f"conversations/{conversation_id}"

            response_data = await self._make_request("GET", endpoint)

            # Parse the response into our model
            return ChatwootConversation(
                id=response_data["id"],
                status=response_data["status"],
                priority=response_data.get("priority"),
                agent_last_seen_at=datetime.fromisoformat(response_data["agent_last_seen_at"].replace("Z", "+00:00"))
                if response_data.get("agent_last_seen_at")
                else None,
                assignee=response_data.get("assignee"),
                contact_last_seen_at=datetime.fromisoformat(
                    response_data["contact_last_seen_at"].replace("Z", "+00:00")
                )
                if response_data.get("contact_last_seen_at")
                else None,
                timestamp=datetime.fromisoformat(response_data["timestamp"].replace("Z", "+00:00"))
                if response_data.get("timestamp")
                else None,
                meta=response_data.get("meta", {}),
                custom_attributes=response_data.get("custom_attributes", {}),
            )

        except Exception as e:
            logger.error("chatwoot_get_conversation_failed", conversation_id=conversation_id, error=str(e))
            raise ChatwootServiceError(f"Failed to get conversation: {str(e)}")

    async def update_conversation_status(self, conversation_id: int, status: str) -> ChatwootApiResponse:
        """Update the status of a Chatwoot conversation.

        Args:
            conversation_id: The Chatwoot conversation ID
            status: The new status (open, resolved, pending)

        Returns:
            ChatwootApiResponse: The API response

        Raises:
            ChatwootServiceError: If updating the status fails
        """
        try:
            endpoint = f"conversations/{conversation_id}/toggle_status"
            data = {"status": status}

            logger.info("chatwoot_updating_conversation_status", conversation_id=conversation_id, status=status)

            response_data = await self._make_request("POST", endpoint, data)

            return ChatwootApiResponse(id=response_data.get("id"), message=f"Conversation status updated to {status}")

        except Exception as e:
            logger.error("chatwoot_update_status_failed", conversation_id=conversation_id, status=status, error=str(e))
            raise ChatwootServiceError(f"Failed to update conversation status: {str(e)}")

    async def get_conversation_messages(self, conversation_id: int, limit: int = 20) -> List[ChatwootMessage]:
        """Get messages from a Chatwoot conversation.

        Args:
            conversation_id: The Chatwoot conversation ID
            limit: Maximum number of messages to retrieve

        Returns:
            List[ChatwootMessage]: List of conversation messages

        Raises:
            ChatwootServiceError: If fetching messages fails
        """
        try:
            endpoint = f"conversations/{conversation_id}/messages"
            params = {"limit": limit}

            response_data = await self._make_request("GET", endpoint, params=params)

            messages = []
            for msg_data in response_data:
                message = ChatwootMessage(
                    id=msg_data["id"],
                    content=msg_data["content"] or "",
                    message_type=msg_data["message_type"],
                    content_type=msg_data.get("content_type", "text"),
                    content_attributes=msg_data.get("content_attributes", {}),
                    created_at=datetime.fromisoformat(msg_data["created_at"].replace("Z", "+00:00")),
                    private=msg_data.get("private", False),
                    source_id=msg_data.get("source_id"),
                    sender=msg_data.get("sender"),
                    external_source_ids=msg_data.get("external_source_ids", {}),
                )
                messages.append(message)

            return messages

        except Exception as e:
            logger.error("chatwoot_get_messages_failed", conversation_id=conversation_id, error=str(e))
            raise ChatwootServiceError(f"Failed to get conversation messages: {str(e)}")

    async def mark_conversation_as_read(self, conversation_id: int) -> ChatwootApiResponse:
        """Mark a conversation as read by the agent.

        Args:
            conversation_id: The Chatwoot conversation ID

        Returns:
            ChatwootApiResponse: The API response

        Raises:
            ChatwootServiceError: If marking as read fails
        """
        try:
            endpoint = f"conversations/{conversation_id}/update_last_seen"

            logger.info("chatwoot_marking_conversation_read", conversation_id=conversation_id)

            await self._make_request("POST", endpoint)

            return ChatwootApiResponse(message="Conversation marked as read")

        except Exception as e:
            logger.error("chatwoot_mark_read_failed", conversation_id=conversation_id, error=str(e))
            raise ChatwootServiceError(f"Failed to mark conversation as read: {str(e)}")

    async def health_check(self) -> bool:
        """Check if the Chatwoot API is accessible.

        Returns:
            bool: True if the API is accessible, False otherwise
        """
        try:
            # Make a simple request to check connectivity
            await self._make_request("GET", "profile")
            return True
        except Exception as e:
            logger.error("chatwoot_health_check_failed", error=str(e))
            return False


# Global service instance
chatwoot_service = ChatwootService()
