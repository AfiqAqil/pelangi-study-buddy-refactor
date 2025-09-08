"""Chatwoot webhook authentication and validation middleware."""

import json
from typing import Callable

from fastapi import HTTPException, Request, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.core.config import settings
from app.core.logging import logger


class ChatwootWebhookMiddleware(BaseHTTPMiddleware):
    """Middleware for authenticating and validating Chatwoot webhooks."""

    def __init__(self, app, webhook_paths: list[str] = None):
        """Initialize the middleware.

        Args:
            app: The FastAPI application instance
            webhook_paths: List of paths that should be validated as Chatwoot webhooks
        """
        super().__init__(app)
        self.webhook_paths = webhook_paths or ["/api/v1/chatwoot/webhook"]

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process webhook authentication for Chatwoot endpoints.

        Args:
            request: The incoming request
            call_next: The next middleware or route handler

        Returns:
            Response: The response from the application

        Raises:
            HTTPException: If webhook authentication fails
        """
        # Only process Chatwoot webhook paths
        if not self._is_chatwoot_webhook_path(request.url.path):
            return await call_next(request)

        # Skip validation if Chatwoot is not enabled
        if not settings.CHATWOOT_ENABLED:
            logger.warning("chatwoot_webhook_disabled", path=request.url.path)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Chatwoot integration is disabled"
            )

        try:
            # Read request body for debugging
            body = await request.body()

            # Store body in request state for later use (since body can only be read once)
            request.state.body = body

            # Validate basic webhook structure (no signature validation needed for Chatwoot)
            await self._validate_webhook_payload(request)

            logger.info("chatwoot_webhook_authenticated", path=request.url.path)

        except HTTPException:
            raise
        except Exception as e:
            logger.error(
                "chatwoot_webhook_auth_error",
                error=str(e),
                error_type=type(e).__name__,
                path=request.url.path,
                exc_info=True,
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Webhook authentication failed: {str(e)}"
            )

        return await call_next(request)

    def _is_chatwoot_webhook_path(self, path: str) -> bool:
        """Check if the request path is a Chatwoot webhook endpoint.

        Args:
            path: The request path

        Returns:
            bool: True if this is a Chatwoot webhook path
        """
        return any(path.startswith(webhook_path) for webhook_path in self.webhook_paths)

    async def _validate_webhook_payload(self, request: Request) -> None:
        """Validate basic webhook payload structure.

        Args:
            request: The incoming request

        Raises:
            HTTPException: If payload validation fails
        """
        # Check content type
        content_type = request.headers.get("content-type", "")
        if not content_type.startswith("application/json"):
            logger.warning("chatwoot_webhook_invalid_content_type", content_type=content_type, path=request.url.path)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid content type. Expected application/json"
            )

        # Validate JSON payload structure
        try:
            # Use the stored body (already read in dispatch method)
            body = getattr(request.state, "body", b"")
            if not body:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty webhook payload")

            payload = json.loads(body.decode("utf-8"))

            # Check for required fields
            required_fields = ["event", "account", "inbox", "conversation"]
            missing_fields = [field for field in required_fields if field not in payload]

            if missing_fields:
                logger.warning("chatwoot_webhook_missing_fields", missing_fields=missing_fields, path=request.url.path)
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Missing required fields: {', '.join(missing_fields)}",
                )

        except json.JSONDecodeError as e:
            logger.warning("chatwoot_webhook_invalid_json", error=str(e), path=request.url.path)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON payload")

        except HTTPException:
            raise
        except Exception as e:
            logger.error("chatwoot_webhook_payload_validation_error", error=str(e), path=request.url.path)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Payload validation failed")
