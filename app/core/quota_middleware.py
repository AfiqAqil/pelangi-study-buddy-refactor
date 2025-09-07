"""Quota validation middleware for API endpoints."""

from typing import Callable, Optional
from fastapi import Request, Response
from fastapi.responses import JSONResponse
import asyncio
import time

from app.core.logging import logger
from app.services.quota_service import quota_service, QuotaValidationResult


class QuotaMiddleware:
    """Middleware for quota validation and recording."""

    def __init__(self):
        """Initialize quota middleware."""
        self.quota_exempt_paths = {
            "/api/v1/auth/",
            "/api/v1/health",
            "/api/v1/subjects/",  # Allow subject browsing without quota
            "/docs",
            "/openapi.json",
            "/redoc",
        }

        # Define which endpoints require which quota types
        self.quota_rules = {
            # Chat endpoints require message quota
            "/api/v1/chatbot/chat": "message",
            "/api/v1/chatbot/stream": "message",
            "/api/v1/chatwoot/webhook": "message",  # Chatwoot messages
            # Quiz endpoints would require quiz quota (when implemented)
            # "/api/v1/quiz/generate": "quiz",
            # "/api/v1/quiz/attempt": "quiz",
        }

    async def __call__(self, request: Request, call_next: Callable) -> Response:
        """Process request with quota validation.

        Args:
            request: FastAPI request
            call_next: Next middleware/endpoint in chain

        Returns:
            Response from the endpoint or quota error
        """
        start_time = time.time()

        try:
            # Skip quota validation for exempt paths
            if self._is_exempt_path(request.url.path):
                response = await call_next(request)
                return response

            # Skip for non-POST requests (GET requests typically don't consume quota)
            if request.method not in ["POST", "PUT"]:
                response = await call_next(request)
                return response

            # Get quota type for this endpoint
            quota_type = self._get_quota_type(request.url.path)
            if not quota_type:
                # No quota rule defined, proceed normally
                response = await call_next(request)
                return response

            # Extract user ID from session/auth
            user_id = await self._extract_user_id(request)
            if not user_id:
                # No user authentication, skip quota (let auth middleware handle)
                response = await call_next(request)
                return response

            # Validate quota before processing request
            quota_result = await self._validate_quota(user_id, quota_type)

            if not quota_result.is_valid:
                logger.warning(
                    "quota_limit_exceeded",
                    user_id=user_id,
                    quota_type=quota_type,
                    current_usage=quota_result.current_usage,
                    daily_limit=quota_result.daily_limit,
                )

                return JSONResponse(
                    status_code=429,
                    content={
                        "error": "Quota limit exceeded",
                        "message": f"You have reached your daily {quota_type} limit.",
                        "quota_status": {
                            "current_usage": quota_result.current_usage,
                            "daily_limit": quota_result.daily_limit,
                            "remaining": quota_result.remaining,
                            "tier": quota_result.tier,
                            "quota_type": quota_result.quota_type,
                        },
                        "upgrade_prompt": quota_result.upgrade_prompt,
                    },
                )

            # Process the request
            response = await call_next(request)

            # Record quota usage after successful request
            # Only record if the response was successful (2xx status codes)
            if 200 <= response.status_code < 300:
                asyncio.create_task(self._record_quota_usage(user_id, quota_type, response))

            # Add quota headers to response
            self._add_quota_headers(response, quota_result)

            processing_time = time.time() - start_time
            logger.info(
                "quota_middleware_completed",
                user_id=user_id,
                quota_type=quota_type,
                processing_time=processing_time,
                status_code=response.status_code,
            )

            return response

        except Exception as e:
            logger.error("quota_middleware_error", error=str(e), path=request.url.path)
            # On middleware error, allow request to proceed (fail-safe)
            response = await call_next(request)
            return response

    def _is_exempt_path(self, path: str) -> bool:
        """Check if path is exempt from quota validation."""
        return any(path.startswith(exempt_path) for exempt_path in self.quota_exempt_paths)

    def _get_quota_type(self, path: str) -> Optional[str]:
        """Get quota type for a given path."""
        for endpoint_path, quota_type in self.quota_rules.items():
            if path.startswith(endpoint_path):
                return quota_type
        return None

    async def _extract_user_id(self, request: Request) -> Optional[str]:
        """Extract user ID from request authentication."""
        try:
            # Try to get user from session token
            from app.utils.auth import get_session_from_token

            # Get authorization header
            auth_header = request.headers.get("Authorization")
            if not auth_header or not auth_header.startswith("Bearer "):
                return None

            token = auth_header.split(" ")[1]
            session = await get_session_from_token(token)

            if session:
                return session.user_id

            return None

        except Exception as e:
            logger.debug("failed_to_extract_user_id", error=str(e))
            return None

    async def _validate_quota(self, user_id: str, quota_type: str) -> QuotaValidationResult:
        """Validate user's quota for the given type."""
        try:
            if quota_type == "message":
                return await quota_service.validate_message_request(user_id)
            elif quota_type == "quiz":
                return await quota_service.validate_quiz_request(user_id)
            else:
                logger.warning("unknown_quota_type", quota_type=quota_type)
                # Return valid result for unknown types (fail-safe)
                return QuotaValidationResult(
                    is_valid=True,
                    current_usage=0,
                    daily_limit=999999,
                    remaining=999999,
                    tier="UNKNOWN",
                    quota_type=quota_type,
                )

        except Exception as e:
            logger.error("quota_validation_error", error=str(e), user_id=user_id, quota_type=quota_type)
            # Fail-safe: allow request on validation error
            return QuotaValidationResult(
                is_valid=True,
                current_usage=0,
                daily_limit=999999,
                remaining=999999,
                tier="ERROR",
                quota_type=quota_type,
            )

    async def _record_quota_usage(self, user_id: str, quota_type: str, response: Response) -> None:
        """Record quota usage after successful request."""
        try:
            if quota_type == "message":
                await quota_service.record_message_sent(user_id)
            elif quota_type == "quiz":
                # For quiz, we need to determine if it was answered correctly
                # This would typically be extracted from the response or request body
                # For now, just record as attempted
                await quota_service.record_quiz_attempt(user_id, answered=False)

            logger.debug("quota_usage_recorded", user_id=user_id, quota_type=quota_type)

        except Exception as e:
            logger.error("quota_recording_error", error=str(e), user_id=user_id, quota_type=quota_type)
            # Don't raise exception as request has already been processed

    def _add_quota_headers(self, response: Response, quota_result: QuotaValidationResult) -> None:
        """Add quota information to response headers."""
        try:
            response.headers["X-Quota-Type"] = quota_result.quota_type
            response.headers["X-Quota-Current"] = str(quota_result.current_usage)
            response.headers["X-Quota-Limit"] = str(quota_result.daily_limit)
            response.headers["X-Quota-Remaining"] = str(quota_result.remaining)
            response.headers["X-User-Tier"] = quota_result.tier

        except Exception as e:
            logger.debug("failed_to_add_quota_headers", error=str(e))
            # Non-critical error, don't fail the response


# Create middleware instance
quota_middleware = QuotaMiddleware()
