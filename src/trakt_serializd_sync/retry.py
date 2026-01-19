# AI-generated: Retry utilities with exponential backoff
"""Retry utilities for handling transient API failures."""

from __future__ import annotations

import logging
import time
from functools import wraps
from typing import Callable, TypeVar

from trakt_serializd_sync.exceptions import (
    SerializdError,
    SyncError,
    TraktError,
    TraktRateLimitError,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")


def retry_with_backoff(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    retryable_exceptions: tuple[type[Exception], ...] = (
        TraktError,
        SerializdError,
        ConnectionError,
        TimeoutError,
    ),
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator that retries a function with exponential backoff.
    
    Args:
        max_retries: Maximum number of retry attempts.
        base_delay: Initial delay in seconds.
        max_delay: Maximum delay between retries.
        exponential_base: Base for exponential backoff calculation.
        retryable_exceptions: Tuple of exception types to retry on.
    
    Returns:
        Decorated function with retry logic.
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            last_exception: Exception | None = None
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except TraktRateLimitError as e:
                    # Special handling for rate limits - use their retry_after
                    if attempt < max_retries:
                        delay = min(e.retry_after, max_delay)
                        logger.warning(
                            f"Rate limited, waiting {delay}s before retry "
                            f"(attempt {attempt + 1}/{max_retries + 1})"
                        )
                        time.sleep(delay)
                        last_exception = e
                    else:
                        raise
                except retryable_exceptions as e:
                    last_exception = e
                    if attempt < max_retries:
                        delay = min(
                            base_delay * (exponential_base ** attempt),
                            max_delay
                        )
                        logger.warning(
                            f"{type(e).__name__}: {e}. "
                            f"Retrying in {delay:.1f}s "
                            f"(attempt {attempt + 1}/{max_retries + 1})"
                        )
                        time.sleep(delay)
                    else:
                        raise
            
            # Should not reach here, but just in case
            if last_exception:
                raise last_exception
            raise SyncError("Retry logic failed unexpectedly")
        
        return wrapper
    return decorator


class RetryContext:
    """
    Context manager for retry operations with state tracking.
    
    Example:
        async with RetryContext(max_retries=3) as retry:
            while retry.should_continue():
                try:
                    result = await api_call()
                    break
                except TransientError as e:
                    retry.record_failure(e)
    """
    
    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
    ):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.attempt = 0
        self.last_exception: Exception | None = None
    
    def __enter__(self) -> RetryContext:
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        return False
    
    def should_continue(self) -> bool:
        """Check if we should attempt another retry."""
        return self.attempt <= self.max_retries
    
    def record_failure(self, exception: Exception) -> None:
        """Record a failure and apply backoff delay."""
        self.last_exception = exception
        self.attempt += 1
        
        if self.attempt <= self.max_retries:
            if isinstance(exception, TraktRateLimitError):
                delay = min(exception.retry_after, self.max_delay)
            else:
                delay = min(
                    self.base_delay * (2 ** (self.attempt - 1)),
                    self.max_delay
                )
            
            logger.warning(
                f"Attempt {self.attempt}/{self.max_retries + 1} failed: {exception}. "
                f"Retrying in {delay:.1f}s"
            )
            time.sleep(delay)
    
    def raise_if_exhausted(self) -> None:
        """Raise the last exception if retries are exhausted."""
        if self.attempt > self.max_retries and self.last_exception:
            raise self.last_exception
