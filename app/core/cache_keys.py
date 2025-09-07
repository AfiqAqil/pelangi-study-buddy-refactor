"""Centralized cache key management for consistent caching across the application."""

from typing import Optional


class CacheKeys:
    """Centralized cache key generation to prevent key conflicts and typos."""
    
    # Key prefixes for different data types
    MESSAGE_COUNT_PREFIX = "message_count"
    WINDOWED_MESSAGE_COUNT_PREFIX = "windowed_message_count"
    CONVERSATION_PREFIX = "conversation"
    CONTACT_PREFIX = "contact"
    USER_SESSION_PREFIX = "user_session"
    API_RATE_LIMIT_PREFIX = "rate_limit"
    
    # Separator for key components
    SEPARATOR = ":"

    @classmethod
    def message_count(cls, session_id: str) -> str:
        """Generate cache key for message count.
        
        Args:
            session_id: Session identifier
            
        Returns:
            Cache key for message count
        """
        return f"{cls.MESSAGE_COUNT_PREFIX}{cls.SEPARATOR}{session_id}"

    @classmethod
    def windowed_message_count(cls, session_id: str, context_window_size: int) -> str:
        """Generate cache key for windowed message count.
        
        Args:
            session_id: Session identifier
            context_window_size: Size of the context window
            
        Returns:
            Cache key for windowed message count
        """
        return f"{cls.WINDOWED_MESSAGE_COUNT_PREFIX}{cls.SEPARATOR}{session_id}{cls.SEPARATOR}{context_window_size}"

    @classmethod
    def conversation(cls, conversation_id: int) -> str:
        """Generate cache key for Chatwoot conversation data.
        
        Args:
            conversation_id: Chatwoot conversation ID
            
        Returns:
            Cache key for conversation data
        """
        return f"{cls.CONVERSATION_PREFIX}{cls.SEPARATOR}{conversation_id}"

    @classmethod
    def contact(cls, contact_id: int) -> str:
        """Generate cache key for Chatwoot contact data.
        
        Args:
            contact_id: Chatwoot contact ID
            
        Returns:
            Cache key for contact data
        """
        return f"{cls.CONTACT_PREFIX}{cls.SEPARATOR}{contact_id}"

    @classmethod
    def user_session(cls, user_id: str, session_id: Optional[str] = None) -> str:
        """Generate cache key for user session data.
        
        Args:
            user_id: User identifier
            session_id: Optional session identifier for user-session specific data
            
        Returns:
            Cache key for user session data
        """
        if session_id:
            return f"{cls.USER_SESSION_PREFIX}{cls.SEPARATOR}{user_id}{cls.SEPARATOR}{session_id}"
        return f"{cls.USER_SESSION_PREFIX}{cls.SEPARATOR}{user_id}"

    @classmethod
    def rate_limit(cls, identifier: str, endpoint: str) -> str:
        """Generate cache key for rate limiting.
        
        Args:
            identifier: Client identifier (IP, user ID, etc.)
            endpoint: API endpoint being rate limited
            
        Returns:
            Cache key for rate limit data
        """
        return f"{cls.API_RATE_LIMIT_PREFIX}{cls.SEPARATOR}{endpoint}{cls.SEPARATOR}{identifier}"

    @classmethod
    def custom(cls, prefix: str, *components: str) -> str:
        """Generate custom cache key with prefix and components.
        
        Args:
            prefix: Cache key prefix
            *components: Key components to join
            
        Returns:
            Custom cache key
        """
        return cls.SEPARATOR.join([prefix] + list(components))

    @classmethod
    def validate_key(cls, key: str) -> bool:
        """Validate that a cache key follows the expected format.
        
        Args:
            key: Cache key to validate
            
        Returns:
            True if key is valid
        """
        # Basic validation: non-empty, contains separator, no dangerous characters
        if not key or len(key) > 250:  # Redis key length limit
            return False
            
        # Check for dangerous characters that could cause issues
        dangerous_chars = [" ", "\n", "\r", "\t", "\x00"]
        return not any(char in key for char in dangerous_chars)

    @classmethod
    def get_prefix(cls, key: str) -> Optional[str]:
        """Extract prefix from a cache key.
        
        Args:
            key: Cache key
            
        Returns:
            Prefix if found, None otherwise
        """
        if cls.SEPARATOR in key:
            return key.split(cls.SEPARATOR)[0]
        return None

    @classmethod
    def get_components(cls, key: str) -> list[str]:
        """Extract all components from a cache key.
        
        Args:
            key: Cache key
            
        Returns:
            List of key components
        """
        return key.split(cls.SEPARATOR)


class CacheKeyPatterns:
    """Common cache key patterns for bulk operations."""
    
    @classmethod
    def all_message_counts(cls, session_id: str) -> str:
        """Pattern to match all message count keys for a session.
        
        Args:
            session_id: Session identifier
            
        Returns:
            Pattern for matching message count keys
        """
        return f"{CacheKeys.MESSAGE_COUNT_PREFIX}{CacheKeys.SEPARATOR}{session_id}*"

    @classmethod
    def all_conversation_data(cls, conversation_id: int) -> str:
        """Pattern to match all conversation-related keys.
        
        Args:
            conversation_id: Conversation identifier
            
        Returns:
            Pattern for matching conversation keys
        """
        return f"{CacheKeys.CONVERSATION_PREFIX}{CacheKeys.SEPARATOR}{conversation_id}*"

    @classmethod
    def all_user_data(cls, user_id: str) -> str:
        """Pattern to match all user-related keys.
        
        Args:
            user_id: User identifier
            
        Returns:
            Pattern for matching user keys
        """
        return f"*{CacheKeys.SEPARATOR}{user_id}*"

    @classmethod
    def all_rate_limits(cls, endpoint: str) -> str:
        """Pattern to match all rate limit keys for an endpoint.
        
        Args:
            endpoint: API endpoint
            
        Returns:
            Pattern for matching rate limit keys
        """
        return f"{CacheKeys.API_RATE_LIMIT_PREFIX}{CacheKeys.SEPARATOR}{endpoint}{CacheKeys.SEPARATOR}*"