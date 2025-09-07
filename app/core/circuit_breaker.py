"""Circuit breaker pattern implementation for fault tolerance."""

import asyncio
import time
from enum import Enum
from typing import Any, Callable, Optional, Dict
from datetime import datetime, timedelta
from collections import deque

from app.core.logging import logger


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Circuit is broken, fast fail
    HALF_OPEN = "half_open"  # Testing if service recovered


class CircuitBreaker:
    """Circuit breaker for handling failures gracefully."""
    
    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: int = 30,
        expected_exception: type = Exception,
        success_threshold: int = 2,
        window_size: int = 10
    ):
        """Initialize the circuit breaker.
        
        Args:
            name: Name of the circuit breaker (for logging)
            failure_threshold: Number of failures before opening circuit
            recovery_timeout: Seconds to wait before trying half-open
            expected_exception: Exception type to catch
            success_threshold: Successes needed in half-open to close
            window_size: Size of sliding window for tracking calls
        """
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception
        self.success_threshold = success_threshold
        self.window_size = window_size
        
        # State management
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: Optional[datetime] = None
        self._last_state_change: datetime = datetime.utcnow()
        
        # Sliding window for tracking recent calls
        self._call_history: deque = deque(maxlen=window_size)
        
        # Lock for thread safety
        self._lock = asyncio.Lock()
    
    @property
    def state(self) -> CircuitState:
        """Get current circuit state."""
        return self._state
    
    @property
    def is_open(self) -> bool:
        """Check if circuit is open."""
        return self._state == CircuitState.OPEN
    
    @property
    def is_closed(self) -> bool:
        """Check if circuit is closed."""
        return self._state == CircuitState.CLOSED
    
    @property
    def is_half_open(self) -> bool:
        """Check if circuit is half-open."""
        return self._state == CircuitState.HALF_OPEN
    
    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """Execute function with circuit breaker protection.
        
        Args:
            func: Async function to call
            *args: Positional arguments for func
            **kwargs: Keyword arguments for func
            
        Returns:
            Result from func
            
        Raises:
            CircuitOpenError: If circuit is open
            Exception: If func raises an exception
        """
        async with self._lock:
            # Check if we should transition from OPEN to HALF_OPEN
            if self._state == CircuitState.OPEN:
                if self._should_attempt_reset():
                    await self._transition_to_half_open()
                else:
                    raise CircuitOpenError(
                        f"Circuit breaker '{self.name}' is OPEN"
                    )
        
        # Try to execute the function
        try:
            result = await func(*args, **kwargs)
            await self._on_success()
            return result
            
        except self.expected_exception as e:
            await self._on_failure()
            raise
    
    async def _on_success(self):
        """Handle successful call."""
        async with self._lock:
            self._call_history.append(True)
            
            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                
                if self._success_count >= self.success_threshold:
                    await self._transition_to_closed()
            
            elif self._state == CircuitState.CLOSED:
                # Reset failure count on success in closed state
                self._failure_count = 0
    
    async def _on_failure(self):
        """Handle failed call."""
        async with self._lock:
            self._call_history.append(False)
            self._last_failure_time = datetime.utcnow()
            
            if self._state == CircuitState.CLOSED:
                self._failure_count += 1
                
                if self._failure_count >= self.failure_threshold:
                    await self._transition_to_open()
            
            elif self._state == CircuitState.HALF_OPEN:
                # Single failure in half-open reopens circuit
                await self._transition_to_open()
    
    def _should_attempt_reset(self) -> bool:
        """Check if enough time passed to try reset."""
        if not self._last_failure_time:
            return False
            
        return (
            datetime.utcnow() - self._last_failure_time
        ).total_seconds() >= self.recovery_timeout
    
    async def _transition_to_open(self):
        """Transition to OPEN state."""
        self._state = CircuitState.OPEN
        self._last_state_change = datetime.utcnow()
        self._failure_count = 0
        self._success_count = 0
        
        logger.warning(
            "circuit_breaker_opened",
            name=self.name,
            failure_threshold=self.failure_threshold
        )
    
    async def _transition_to_closed(self):
        """Transition to CLOSED state."""
        previous_state = self._state
        self._state = CircuitState.CLOSED
        self._last_state_change = datetime.utcnow()
        self._failure_count = 0
        self._success_count = 0
        
        logger.info(
            "circuit_breaker_closed",
            name=self.name,
            previous_state=previous_state.value
        )
    
    async def _transition_to_half_open(self):
        """Transition to HALF_OPEN state."""
        self._state = CircuitState.HALF_OPEN
        self._last_state_change = datetime.utcnow()
        self._success_count = 0
        
        logger.info(
            "circuit_breaker_half_open",
            name=self.name,
            recovery_timeout=self.recovery_timeout
        )
    
    def get_stats(self) -> Dict[str, Any]:
        """Get circuit breaker statistics.
        
        Returns:
            Statistics dictionary
        """
        total_calls = len(self._call_history)
        failures = self._call_history.count(False)
        successes = self._call_history.count(True)
        
        return {
            "name": self.name,
            "state": self._state.value,
            "failure_count": self._failure_count,
            "success_count": self._success_count,
            "total_calls": total_calls,
            "recent_failures": failures,
            "recent_successes": successes,
            "failure_rate": failures / total_calls if total_calls > 0 else 0,
            "last_failure_time": self._last_failure_time.isoformat() if self._last_failure_time else None,
            "last_state_change": self._last_state_change.isoformat(),
            "time_in_current_state": (
                datetime.utcnow() - self._last_state_change
            ).total_seconds()
        }
    
    async def reset(self):
        """Manually reset the circuit breaker."""
        async with self._lock:
            await self._transition_to_closed()
            self._call_history.clear()
            self._last_failure_time = None
            
            logger.info("circuit_breaker_manually_reset", name=self.name)


class CircuitOpenError(Exception):
    """Exception raised when circuit is open."""
    pass


class CircuitBreakerManager:
    """Manages multiple circuit breakers."""
    
    def __init__(self):
        """Initialize the circuit breaker manager."""
        self._breakers: Dict[str, CircuitBreaker] = {}
        self._lock = asyncio.Lock()
    
    async def get_or_create(
        self,
        name: str,
        **kwargs
    ) -> CircuitBreaker:
        """Get existing or create new circuit breaker.
        
        Args:
            name: Circuit breaker name
            **kwargs: Arguments for CircuitBreaker constructor
            
        Returns:
            Circuit breaker instance
        """
        async with self._lock:
            if name not in self._breakers:
                self._breakers[name] = CircuitBreaker(name=name, **kwargs)
                logger.debug("circuit_breaker_created", name=name)
            
            return self._breakers[name]
    
    def get(self, name: str) -> Optional[CircuitBreaker]:
        """Get circuit breaker by name.
        
        Args:
            name: Circuit breaker name
            
        Returns:
            Circuit breaker or None if not found
        """
        return self._breakers.get(name)
    
    async def reset_all(self):
        """Reset all circuit breakers."""
        async with self._lock:
            for breaker in self._breakers.values():
                await breaker.reset()
            
            logger.info(
                "circuit_breakers_reset",
                count=len(self._breakers)
            )
    
    def get_all_stats(self) -> Dict[str, Any]:
        """Get statistics for all circuit breakers.
        
        Returns:
            Dictionary of statistics by breaker name
        """
        return {
            name: breaker.get_stats()
            for name, breaker in self._breakers.items()
        }


# Global circuit breaker manager
circuit_breaker_manager = CircuitBreakerManager()