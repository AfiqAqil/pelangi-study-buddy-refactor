"""Redis service for caching and session management."""

import json
import asyncio
from typing import Optional, Any, Dict, Union
from contextlib import asynccontextmanager

import redis.asyncio as redis
from redis.asyncio import ConnectionPool, Redis

from app.core.config import settings
from app.core.logging import logger


class RedisServiceError(Exception):
    """Exception raised for Redis service errors."""

    pass


class RedisService:
    """Async Redis service for caching and session management."""

    def __init__(self):
        """Initialize the Redis service."""
        self.pool: Optional[ConnectionPool] = None
        self.client: Optional[Redis] = None
        self._connection_lock = asyncio.Lock()

    async def initialize(self) -> None:
        """Initialize Redis connection pool."""
        if not settings.REDIS_ENABLED:
            logger.info("redis_disabled", message="Redis is disabled via configuration")
            return

        try:
            async with self._connection_lock:
                if self.pool is None:
                    # Create connection pool
                    if settings.REDIS_URL:
                        self.pool = ConnectionPool.from_url(
                            settings.REDIS_URL,
                            max_connections=settings.REDIS_MAX_CONNECTIONS,
                            socket_connect_timeout=settings.REDIS_SOCKET_CONNECT_TIMEOUT,
                            socket_keepalive=settings.REDIS_SOCKET_KEEPALIVE,
                            socket_keepalive_options=settings.REDIS_SOCKET_KEEPALIVE_OPTIONS,
                            decode_responses=True,
                            retry_on_timeout=True,
                        )
                    else:
                        self.pool = ConnectionPool(
                            host=settings.REDIS_HOST,
                            port=settings.REDIS_PORT,
                            db=settings.REDIS_DB,
                            password=settings.REDIS_PASSWORD if settings.REDIS_PASSWORD else None,
                            max_connections=settings.REDIS_MAX_CONNECTIONS,
                            socket_connect_timeout=settings.REDIS_SOCKET_CONNECT_TIMEOUT,
                            socket_keepalive=settings.REDIS_SOCKET_KEEPALIVE,
                            socket_keepalive_options=settings.REDIS_SOCKET_KEEPALIVE_OPTIONS,
                            decode_responses=True,
                            retry_on_timeout=True,
                        )

                    self.client = Redis(connection_pool=self.pool)

                    # Test connection
                    await self.client.ping()
                    logger.info(
                        "redis_initialized", host=settings.REDIS_HOST, port=settings.REDIS_PORT, db=settings.REDIS_DB
                    )

        except Exception as e:
            logger.error("redis_initialization_failed", error=str(e))
            self.pool = None
            self.client = None
            if settings.ENVIRONMENT.value == "production":
                # In production, continue without Redis rather than failing
                logger.warning("redis_fallback_mode", message="Continuing without Redis cache")
            else:
                # In development, we might want to know about Redis issues
                raise RedisServiceError(f"Failed to initialize Redis: {str(e)}")

    async def close(self) -> None:
        """Close Redis connections."""
        try:
            if self.client:
                await self.client.aclose()
            if self.pool:
                await self.pool.aclose()
            self.client = None
            self.pool = None
            logger.info("redis_connections_closed")
        except Exception as e:
            logger.error("redis_close_failed", error=str(e))

    @asynccontextmanager
    async def get_client(self):
        """Get Redis client with connection management."""
        if not self.is_available():
            yield None
            return

        try:
            if self.client is None:
                await self.initialize()
            yield self.client
        except Exception as e:
            logger.error("redis_client_error", error=str(e))
            yield None

    def is_available(self) -> bool:
        """Check if Redis is available and enabled."""
        return settings.REDIS_ENABLED and self.client is not None

    async def get(self, key: str, default: Any = None) -> Any:
        """Get a value from Redis cache.

        Args:
            key: Cache key
            default: Default value if key not found

        Returns:
            Cached value or default
        """
        async with self.get_client() as client:
            if client is None:
                return default

            try:
                value = await client.get(key)
                if value is None:
                    return default

                # Try to deserialize JSON, fallback to string
                try:
                    return json.loads(value)
                except (json.JSONDecodeError, TypeError):
                    return value

            except Exception as e:
                logger.error("redis_get_failed", key=key, error=str(e))
                return default

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set a value in Redis cache.

        Args:
            key: Cache key
            value: Value to cache
            ttl: Time to live in seconds

        Returns:
            True if successful, False otherwise
        """
        async with self.get_client() as client:
            if client is None:
                return False

            try:
                # Serialize value
                if isinstance(value, (dict, list, tuple)):
                    serialized_value = json.dumps(value)
                else:
                    serialized_value = str(value)

                ttl = ttl or settings.CACHE_TTL_SECONDS
                result = await client.set(key, serialized_value, ex=ttl)

                logger.debug("redis_set_success", key=key, ttl=ttl)
                return bool(result)

            except Exception as e:
                logger.error("redis_set_failed", key=key, error=str(e))
                return False

    async def delete(self, key: str) -> bool:
        """Delete a key from Redis cache.

        Args:
            key: Cache key to delete

        Returns:
            True if key was deleted, False otherwise
        """
        async with self.get_client() as client:
            if client is None:
                return False

            try:
                result = await client.delete(key)
                logger.debug("redis_delete", key=key, deleted=bool(result))
                return bool(result)

            except Exception as e:
                logger.error("redis_delete_failed", key=key, error=str(e))
                return False

    async def increment(self, key: str, amount: int = 1) -> Optional[int]:
        """Increment a numeric value in Redis.

        Args:
            key: Cache key
            amount: Amount to increment by

        Returns:
            New value after increment, or None if failed
        """
        async with self.get_client() as client:
            if client is None:
                return None

            try:
                result = await client.incrby(key, amount)
                logger.debug("redis_increment", key=key, amount=amount, new_value=result)
                return result

            except Exception as e:
                logger.error("redis_increment_failed", key=key, error=str(e))
                return None

    async def exists(self, key: str) -> bool:
        """Check if a key exists in Redis.

        Args:
            key: Cache key to check

        Returns:
            True if key exists, False otherwise
        """
        async with self.get_client() as client:
            if client is None:
                return False

            try:
                result = await client.exists(key)
                return bool(result)

            except Exception as e:
                logger.error("redis_exists_failed", key=key, error=str(e))
                return False

    # Specialized methods for common use cases

    async def get_message_count(self, session_id: str) -> Optional[int]:
        """Get cached message count for a session.

        Args:
            session_id: Session identifier

        Returns:
            Message count or None if not cached
        """
        key = f"message_count:{session_id}"
        count = await self.get(key)
        return int(count) if count is not None else None

    async def set_message_count(self, session_id: str, count: int, ttl: Optional[int] = None) -> bool:
        """Cache message count for a session.

        Args:
            session_id: Session identifier
            count: Message count to cache
            ttl: Time to live in seconds

        Returns:
            True if successful
        """
        key = f"message_count:{session_id}"
        ttl = ttl or settings.CACHE_MESSAGE_COUNT_TTL
        return await self.set(key, count, ttl)

    async def invalidate_message_count(self, session_id: str) -> bool:
        """Invalidate cached message count for a session.

        Args:
            session_id: Session identifier

        Returns:
            True if deleted
        """
        key = f"message_count:{session_id}"
        return await self.delete(key)

    async def cache_conversation_info(
        self, conversation_id: int, info: Dict[str, Any], ttl: Optional[int] = None
    ) -> bool:
        """Cache conversation information.

        Args:
            conversation_id: Chatwoot conversation ID
            info: Conversation information to cache
            ttl: Time to live in seconds

        Returns:
            True if successful
        """
        key = f"conversation:{conversation_id}"
        ttl = ttl or settings.CACHE_CONVERSATION_TTL
        return await self.set(key, info, ttl)

    async def get_conversation_info(self, conversation_id: int) -> Optional[Dict[str, Any]]:
        """Get cached conversation information.

        Args:
            conversation_id: Chatwoot conversation ID

        Returns:
            Conversation info or None if not cached
        """
        key = f"conversation:{conversation_id}"
        return await self.get(key)

    async def cache_contact_info(self, contact_id: int, info: Dict[str, Any], ttl: Optional[int] = None) -> bool:
        """Cache contact information.

        Args:
            contact_id: Chatwoot contact ID
            info: Contact information to cache
            ttl: Time to live in seconds

        Returns:
            True if successful
        """
        key = f"contact:{contact_id}"
        ttl = ttl or settings.CACHE_CONTACT_TTL
        return await self.set(key, info, ttl)

    async def get_contact_info(self, contact_id: int) -> Optional[Dict[str, Any]]:
        """Get cached contact information.

        Args:
            contact_id: Chatwoot contact ID

        Returns:
            Contact info or None if not cached
        """
        key = f"contact:{contact_id}"
        return await self.get(key)

    async def health_check(self) -> Dict[str, Any]:
        """Check Redis health status.

        Returns:
            Health status information
        """
        health = {"enabled": settings.REDIS_ENABLED, "connected": False, "ping_successful": False, "error": None}

        if not settings.REDIS_ENABLED:
            return health

        async with self.get_client() as client:
            if client is None:
                health["error"] = "No Redis client available"
                return health

            try:
                health["connected"] = True
                await client.ping()
                health["ping_successful"] = True

            except Exception as e:
                health["error"] = str(e)
                logger.error("redis_health_check_failed", error=str(e))

        return health


# Global Redis service instance
redis_service = RedisService()
