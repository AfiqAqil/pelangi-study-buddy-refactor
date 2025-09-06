"""Caching utilities and decorators for performance optimization."""

import functools
import hashlib
import json
import time
from typing import Any, Callable, Optional, Union

from app.core.logging import logger
from app.services.redis import redis_service


def cache_key_from_args(*args, **kwargs) -> str:
    """Generate a cache key from function arguments.

    Args:
        *args: Positional arguments
        **kwargs: Keyword arguments

    Returns:
        String cache key
    """
    # Create a deterministic string from args and kwargs
    key_data = {"args": args, "kwargs": kwargs}

    # Convert to JSON string and hash for consistent key
    key_string = json.dumps(key_data, sort_keys=True, default=str)
    key_hash = hashlib.md5(key_string.encode()).hexdigest()

    return key_hash


def redis_cache(prefix: str, ttl: Optional[int] = None, include_self: bool = True):
    """Decorator to cache function results in Redis.

    Args:
        prefix: Cache key prefix
        ttl: Time to live in seconds
        include_self: Whether to include 'self' in cache key for instance methods

    Returns:
        Decorated function
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # Skip caching if Redis is not available
            if not redis_service.is_available():
                logger.debug("redis_cache_skip", function=func.__name__, reason="Redis not available")
                return await func(*args, **kwargs)

            # Generate cache key
            cache_args = args
            if not include_self and args and hasattr(args[0], "__class__"):
                # Skip 'self' for instance methods
                cache_args = args[1:]

            key_suffix = cache_key_from_args(*cache_args, **kwargs)
            cache_key = f"{prefix}:{key_suffix}"

            # Try to get from cache
            start_time = time.time()
            cached_result = await redis_service.get(cache_key)

            if cached_result is not None:
                cache_duration = time.time() - start_time
                logger.debug("cache_hit", function=func.__name__, cache_key=cache_key, duration=cache_duration)
                return cached_result

            # Cache miss - execute function
            logger.debug("cache_miss", function=func.__name__, cache_key=cache_key)
            result = await func(*args, **kwargs)

            # Store in cache
            if result is not None:
                success = await redis_service.set(cache_key, result, ttl)
                if success:
                    total_duration = time.time() - start_time
                    logger.debug(
                        "cache_stored", function=func.__name__, cache_key=cache_key, ttl=ttl, duration=total_duration
                    )
                else:
                    logger.warning("cache_store_failed", function=func.__name__, cache_key=cache_key)

            return result

        return wrapper

    return decorator


def cache_invalidate(prefix: str, *args, **kwargs) -> bool:
    """Invalidate cache entries by key pattern.

    Args:
        prefix: Cache key prefix
        *args: Arguments used to generate cache key
        **kwargs: Keyword arguments used to generate cache key

    Returns:
        True if invalidated successfully
    """

    async def _invalidate():
        if not redis_service.is_available():
            return False

        key_suffix = cache_key_from_args(*args, **kwargs)
        cache_key = f"{prefix}:{key_suffix}"

        result = await redis_service.delete(cache_key)
        logger.debug("cache_invalidated", cache_key=cache_key, success=result)
        return result

    return _invalidate()


class CacheManager:
    """High-level cache management utilities."""

    @staticmethod
    async def warm_cache(session_id: str, message_count: int) -> bool:
        """Pre-warm cache with known values.

        Args:
            session_id: Session identifier
            message_count: Current message count

        Returns:
            True if successful
        """
        success = await redis_service.set_message_count(session_id, message_count)
        if success:
            logger.debug("cache_warmed", session_id=session_id, message_count=message_count)
        return success

    @staticmethod
    async def invalidate_session_cache(session_id: str) -> bool:
        """Invalidate all cache entries for a session.

        Args:
            session_id: Session identifier to invalidate

        Returns:
            True if successful
        """
        success = await redis_service.invalidate_message_count(session_id)
        if success:
            logger.debug("session_cache_invalidated", session_id=session_id)
        return success

    @staticmethod
    async def get_cache_stats() -> dict:
        """Get cache statistics and health information.

        Returns:
            Dictionary with cache statistics
        """
        redis_health = await redis_service.health_check()

        stats = {"redis_health": redis_health, "cache_enabled": redis_service.is_available(), "timestamp": time.time()}

        return stats


class ConversationCache:
    """Specialized caching for conversation data."""

    @staticmethod
    async def get_or_set_message_count(session_id: str, fetch_func: Callable, ttl: Optional[int] = None) -> int:
        """Get message count from cache or fetch and cache it.

        Args:
            session_id: Session identifier
            fetch_func: Async function to fetch the count if not cached
            ttl: Time to live for cache entry

        Returns:
            Message count
        """
        # Try cache first
        cached_count = await redis_service.get_message_count(session_id)
        if cached_count is not None:
            logger.debug("message_count_cache_hit", session_id=session_id, count=cached_count)
            return cached_count

        # Cache miss - fetch and cache
        logger.debug("message_count_cache_miss", session_id=session_id)
        count = await fetch_func()

        if count is not None:
            await redis_service.set_message_count(session_id, count, ttl)
            logger.debug("message_count_cached", session_id=session_id, count=count)

        return count or 0


# Cache decorators for common patterns
def cache_message_count(ttl: Optional[int] = None):
    """Cache decorator specifically for message count functions."""
    return redis_cache("msg_count", ttl or 300, include_self=True)


def cache_conversation_data(ttl: Optional[int] = None):
    """Cache decorator for conversation data."""
    return redis_cache("conv_data", ttl or 1800, include_self=True)


def cache_contact_data(ttl: Optional[int] = None):
    """Cache decorator for contact data."""
    return redis_cache("contact_data", ttl or 3600, include_self=True)


# Performance monitoring decorator
def monitor_performance(operation_name: str):
    """Decorator to monitor function performance with metrics.

    Args:
        operation_name: Name of the operation for metrics

    Returns:
        Decorated function
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.time()

            try:
                result = await func(*args, **kwargs)
                duration = time.time() - start_time

                logger.debug(
                    "operation_completed",
                    operation=operation_name,
                    function=func.__name__,
                    duration=duration,
                    status="success",
                )

                return result

            except Exception as e:
                duration = time.time() - start_time
                logger.error(
                    "operation_failed",
                    operation=operation_name,
                    function=func.__name__,
                    duration=duration,
                    status="error",
                    error=str(e),
                )
                raise

        return wrapper

    return decorator
