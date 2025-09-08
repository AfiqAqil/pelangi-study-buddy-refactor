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
from app.core.circuit_breaker import circuit_breaker_manager, CircuitOpenError
from app.schemas.chatwoot import (
    ChatwootApiMessage,
    ChatwootApiResponse,
    ChatwootConversation,
    ChatwootContact,
    ChatwootMessage,
    ChatwootAttachment,
)


class ChatwootServiceError(Exception):
    """Exception raised for Chatwoot service errors."""

    pass


class ChatwootService:
    """Service for interacting with the Chatwoot API with connection pooling."""

    def __init__(self):
        """Initialize the Chatwoot service with configuration and connection pool."""
        self.base_url = settings.CHATWOOT_BASE_URL.rstrip("/")
        self.api_access_token = settings.CHATWOOT_API_ACCESS_TOKEN
        self.account_id = settings.CHATWOOT_ACCOUNT_ID
        self.timeout = ClientTimeout(total=settings.CHATWOOT_TIMEOUT)
        self.max_retries = settings.CHATWOOT_MAX_RETRIES

        # HTTP session and connection pool
        self.connector = None
        self.session = None

        # Circuit breaker for API calls
        self.circuit_breaker = None

        # Validate configuration
        if not all([self.base_url, self.api_access_token, self.account_id]):
            logger.warning(
                "chatwoot_service_incomplete_config",
                base_url=bool(self.base_url),
                api_token=bool(self.api_access_token),
                account_id=bool(self.account_id),
            )

    async def _get_circuit_breaker(self):
        """Get or create circuit breaker for API calls."""
        if self.circuit_breaker is None:
            self.circuit_breaker = await circuit_breaker_manager.get_or_create(
                name="chatwoot_api",
                failure_threshold=3,  # Open after 3 failures
                recovery_timeout=30,  # Try recovery after 30 seconds
                success_threshold=2,  # Need 2 successes to close
                window_size=10,  # Track last 10 calls
                expected_exception=ChatwootServiceError,
            )
        return self.circuit_breaker

    def _get_connection_pool_config(self) -> dict:
        """Get environment-specific connection pool configuration.

        Returns:
            Dict with connection pool settings
        """
        from app.core.config import Environment

        if settings.ENVIRONMENT == Environment.PRODUCTION:
            return {
                "limit": 200,  # High concurrency for production
                "limit_per_host": 50,
                "keepalive_timeout": 180,
                "ttl_dns_cache": 300,  # 5 minutes
            }
        elif settings.ENVIRONMENT == Environment.STAGING:
            return {
                "limit": 100,  # Medium concurrency for staging
                "limit_per_host": 30,
                "keepalive_timeout": 120,
                "ttl_dns_cache": 300,
            }
        else:  # Development/Test
            return {
                "limit": 20,  # Lower limits for development
                "limit_per_host": 10,
                "keepalive_timeout": 60,
                "ttl_dns_cache": 60,  # Faster DNS refresh in dev
            }

    async def _get_session(self):
        """Get or create HTTP session with connection pooling."""
        if self.session is None or self.session.closed:
            # Get environment-specific connection pool config
            pool_config = self._get_connection_pool_config()

            logger.info("chatwoot_connection_pool_config", environment=settings.ENVIRONMENT.value, **pool_config)

            # Create connector with environment-aware connection pooling
            self.connector = aiohttp.TCPConnector(
                limit=pool_config["limit"],
                limit_per_host=pool_config["limit_per_host"],
                keepalive_timeout=pool_config["keepalive_timeout"],
                enable_cleanup_closed=True,  # Clean up closed connections
                use_dns_cache=True,  # Cache DNS lookups
                ttl_dns_cache=pool_config["ttl_dns_cache"],
                family=0,  # Use both IPv4 and IPv6
                force_close=False,  # Reuse connections more aggressively
            )

            # Create session with pooled connector and proper timeout configuration
            timeout = aiohttp.ClientTimeout(
                total=self.timeout.total,  # Overall timeout
                connect=10,  # Connection timeout
                sock_read=self.timeout.total,  # Socket read timeout
            )

            self.session = aiohttp.ClientSession(
                connector=self.connector,
                timeout=timeout,
                headers={
                    "api_access_token": self.api_access_token,
                    "Content-Type": "application/json",
                    "User-Agent": f"FastAPI-LangGraph-Agent/{settings.ENVIRONMENT.value}",
                },
            )

            logger.debug(
                "chatwoot_session_created", pool_limit=100, per_host_limit=30, timeout=settings.CHATWOOT_TIMEOUT
            )

        return self.session

    async def close(self):
        """Close HTTP session and connector."""
        if self.session:
            await self.session.close()
            self.session = None
        if self.connector:
            await self.connector.close()
            self.connector = None
        logger.debug("chatwoot_service_closed")

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Make an HTTP request to the Chatwoot API with circuit breaker and retry logic.

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
        # Get circuit breaker for API calls
        circuit_breaker = await self._get_circuit_breaker()

        async def _execute_request():
            """Execute the actual request - used by circuit breaker."""
            url = f"{self.base_url}/api/v1/accounts/{self.account_id}/{endpoint}"
            request_start_time = time.time()

            for attempt in range(self.max_retries):
                try:
                    # Use pooled session instead of creating new one each time
                    session = await self._get_session()
                    async with session.request(method=method, url=url, json=data, params=params) as response:
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

                            logger.debug(
                                "chatwoot_api_success",
                                method=method,
                                endpoint=endpoint,
                                status=response.status,
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

                            # Don't retry for client errors (4xx) - fail fast
                            if 400 <= response.status < 500:
                                raise ChatwootServiceError(
                                    f"Chatwoot API client error: {response.status} - {response_data}"
                                )

                except ClientError as e:
                    logger.error(
                        "chatwoot_api_client_error",
                        method=method,
                        endpoint=endpoint,
                        error=str(e),
                        attempt=attempt + 1,
                    )

                    # If this is the last attempt, raise the error
                    if attempt == self.max_retries - 1:
                        raise ChatwootServiceError(f"Chatwoot API request failed: {str(e)}")

                    # Fixed minimal backoff for faster recovery
                    await asyncio.sleep(0.5)  # Fixed 0.5s delay between retries

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

                    # Fixed minimal backoff for faster recovery
                    await asyncio.sleep(0.5)  # Fixed 0.5s delay

            # Track failed API request (if we reach this point, all retries failed)
            chatwoot_api_requests_total.labels(endpoint=endpoint, method=method, status="failed").inc()
            raise ChatwootServiceError("Max retries exceeded for Chatwoot API request")

        # Execute request through circuit breaker
        try:
            return await circuit_breaker.call(_execute_request)
        except CircuitOpenError:
            # Circuit is open - return fallback response
            logger.warning(
                "chatwoot_circuit_open",
                method=method,
                endpoint=endpoint,
                message="Circuit breaker is open, falling back",
            )
            # Track circuit breaker metrics
            chatwoot_api_requests_total.labels(endpoint=endpoint, method=method, status="circuit_open").inc()
            raise ChatwootServiceError("Chatwoot service temporarily unavailable (circuit breaker open)")

    async def send_message(self, conversation_id: int, message: ChatwootApiMessage) -> ChatwootApiResponse:
        """Send a message to a Chatwoot conversation.

        Args:
            conversation_id: The Chatwoot conversation ID
            message: The message to send

        Returns:
            ChatwootApiResponse: The API response

        Raises:
            ChatwootServiceError: If sending the message fails
            CircuitOpenError: If circuit breaker is open
        """
        try:
            # Get circuit breaker
            breaker = await self._get_circuit_breaker()

            # Check if circuit is open - fail fast without making request
            if breaker.is_open:
                logger.warning("chatwoot_circuit_open_send_message", conversation_id=conversation_id)
                raise CircuitOpenError("Chatwoot API circuit is open")

            # Execute with circuit breaker protection
            async def _send():
                endpoint = f"conversations/{conversation_id}/messages"
                data = message.model_dump()

                logger.debug(
                    "chatwoot_sending_message",
                    conversation_id=conversation_id,
                    message_type=message.message_type,
                )

                response_data = await self._make_request("POST", endpoint, data)
                return ChatwootApiResponse(id=response_data.get("id"), message="Message sent successfully")

            return await breaker.call(_send)

        except CircuitOpenError:
            # Re-raise circuit open errors
            raise
        except Exception as e:
            logger.error("chatwoot_send_message_failed", conversation_id=conversation_id, error=str(e))
            raise ChatwootServiceError(f"Failed to send message: {str(e)}")

    async def send_message_with_images(
        self,
        conversation_id: int,
        text_content: str,
        image_data: List[Dict[str, Any]],
        private: bool = False,
    ) -> List[ChatwootApiResponse]:
        """Send a text message followed by image attachments.
        
        Args:
            conversation_id: The Chatwoot conversation ID
            text_content: The main text content
            image_data: List of image data with URLs and metadata
            private: Whether messages should be private notes
            
        Returns:
            List[ChatwootApiResponse]: Responses for all sent messages
            
        Raises:
            ChatwootServiceError: If sending messages fails
        """
        # Images are always enabled - no configuration check needed
        
        responses = []
        
        try:
            # Send main text message first
            text_message = ChatwootApiMessage(
                content=text_content,
                private=private
            )
            text_response = await self.send_message(conversation_id, text_message)
            responses.append(text_response)
            
            # Process and send images
            if image_data:
                # Limit number of images (fixed at 3)
                limited_images = image_data[:3]
                
                logger.debug(
                    "sending_image_attachments",
                    conversation_id=conversation_id,
                    total_images=len(image_data),
                    sending_images=len(limited_images),
                )
                
                for i, image_info in enumerate(limited_images):
                    try:
                        # Add small delay between image messages to avoid rate limiting
                        if i > 0:
                            await asyncio.sleep(0.5)  # Fixed 0.5 second delay
                        
                        # Validate image URL
                        image_url = image_info.get("url", "")
                        if not image_url or not self._is_valid_image_url(image_url):
                            logger.warning(
                                "invalid_image_url_skipped",
                                conversation_id=conversation_id,
                                url=image_url,
                                image_index=i,
                            )
                            continue
                        
                        # Create image message
                        image_caption = self._create_image_caption(image_info)
                        image_message = ChatwootApiMessage(
                            content=image_caption,
                            private=private,
                            attachments=[
                                ChatwootAttachment(
                                    external_url=image_url,
                                    file_type="image",
                                    fallback_text=image_info.get("description", "Educational diagram"),
                                )
                            ]
                        )
                        
                        image_response = await self.send_message(conversation_id, image_message)
                        responses.append(image_response)
                        
                    except Exception as image_error:
                        logger.error(
                            "image_attachment_send_failed",
                            conversation_id=conversation_id,
                            image_index=i,
                            error=str(image_error),
                        )
                        # Continue with other images even if one fails
                        continue
            
            logger.info(
                "message_with_images_sent",
                conversation_id=conversation_id,
                total_messages=len(responses),
                images_sent=len(responses) - 1,
            )
            
            return responses
            
        except Exception as e:
            logger.error(
                "send_message_with_images_failed",
                conversation_id=conversation_id,
                error=str(e),
            )
            raise ChatwootServiceError(f"Failed to send message with images: {str(e)}")
    
    def _is_valid_image_url(self, url: str) -> bool:
        """Validate if the URL is a valid image URL.
        
        Args:
            url: Image URL to validate
            
        Returns:
            bool: True if URL appears to be a valid image
        """
        if not url or not isinstance(url, str):
            return False
        
        # Check if URL starts with http/https
        if not url.startswith(("http://", "https://")):
            return False
        
        # Check for common image extensions
        image_extensions = [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg"]
        url_lower = url.lower()
        
        # Check extension in URL path
        for ext in image_extensions:
            if ext in url_lower:
                return True
        
        # If no extension found, assume it might be a valid image URL
        # (some services serve images without file extensions)
        return True
    
    def _create_image_caption(self, image_info: Dict[str, Any]) -> str:
        """Create a caption for an image attachment.
        
        Args:
            image_info: Image metadata
            
        Returns:
            str: Caption text for the image
        """
        parts = []
        
        # Add description if available
        description = image_info.get("description", "")
        if description:
            parts.append(f"📸 {description}")
        else:
            parts.append("📸 Educational diagram")
        
        # Add source information
        source = image_info.get("source", "")
        page = image_info.get("page")
        if source and page:
            parts.append(f"(Source: {source}, Page {page})")
        elif source:
            parts.append(f"(Source: {source})")
        
        # Add spatial relationship if available
        relationship = image_info.get("spatial_relationship", "")
        if relationship and relationship != "adjacent":
            parts.append(f"[{relationship.title()} related content]")
        
        return " ".join(parts)

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

            logger.debug("chatwoot_updating_conversation_status", conversation_id=conversation_id, status=status)

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
            # Get circuit breaker
            breaker = await self._get_circuit_breaker()

            # For non-critical operations, skip if circuit is open
            if breaker.is_open:
                logger.debug("chatwoot_circuit_open_skipping_mark_read", conversation_id=conversation_id)
                return ChatwootApiResponse(message="Skipped due to circuit open")

            # Execute with circuit breaker protection
            async def _mark_read():
                endpoint = f"conversations/{conversation_id}/update_last_seen"
                logger.debug("chatwoot_marking_conversation_read", conversation_id=conversation_id)
                await self._make_request("POST", endpoint)
                return ChatwootApiResponse(message="Conversation marked as read")

            return await breaker.call(_mark_read)

        except CircuitOpenError:
            # For non-critical operation, just log and return
            logger.debug("chatwoot_mark_read_circuit_open", conversation_id=conversation_id)
            return ChatwootApiResponse(message="Skipped due to circuit open")
        except Exception as e:
            logger.error("chatwoot_mark_read_failed", conversation_id=conversation_id, error=str(e))
            raise ChatwootServiceError(f"Failed to mark conversation as read: {str(e)}")

    async def merge_contacts(self, base_contact_id: int, mergee_contact_id: int) -> Optional[Dict[str, Any]]:
        """Merge two Chatwoot contacts.

        Args:
            base_contact_id: Contact ID to merge into (will be kept)
            mergee_contact_id: Contact ID to merge from (will be deleted)

        Returns:
            Optional[Dict[str, Any]]: Merge result data or None if failed

        Raises:
            ChatwootServiceError: If merging contacts fails
        """
        try:
            endpoint = "actions/contact_merge"
            data = {
                "base_contact_id": base_contact_id,
                "mergee_contact_id": mergee_contact_id,
            }

            logger.info(
                "chatwoot_merging_contacts",
                base_contact_id=base_contact_id,
                mergee_contact_id=mergee_contact_id,
            )

            response_data = await self._make_request("POST", endpoint, data)

            logger.info(
                "chatwoot_contacts_merged_successfully",
                base_contact_id=base_contact_id,
                mergee_contact_id=mergee_contact_id,
            )

            return response_data

        except Exception as e:
            logger.error(
                "chatwoot_merge_contacts_failed",
                base_contact_id=base_contact_id,
                mergee_contact_id=mergee_contact_id,
                error=str(e),
            )
            raise ChatwootServiceError(f"Failed to merge contacts: {str(e)}")

    async def get_contact(self, contact_id: int) -> Optional[ChatwootContact]:
        """Get contact details from Chatwoot.

        Args:
            contact_id: The Chatwoot contact ID

        Returns:
            Optional[ChatwootContact]: The contact details or None if not found

        Raises:
            ChatwootServiceError: If fetching the contact fails
        """
        try:
            endpoint = f"contacts/{contact_id}"

            response_data = await self._make_request("GET", endpoint)

            # Parse the response into our model
            return ChatwootContact(
                id=response_data["id"],
                name=response_data.get("name"),
                email=response_data.get("email"),
                phone=response_data.get("phone_number"),
                identifier=response_data.get("identifier"),
                custom_attributes=response_data.get("custom_attributes", {}),
            )

        except Exception as e:
            logger.error("chatwoot_get_contact_failed", contact_id=contact_id, error=str(e))
            raise ChatwootServiceError(f"Failed to get contact: {str(e)}")

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
