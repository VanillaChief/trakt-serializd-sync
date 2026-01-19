# AI-generated: Core exception classes for the sync tool
"""Custom exceptions for trakt-serializd-sync."""


class SyncError(Exception):
    """Base exception for sync-related errors."""
    pass


class TraktError(SyncError):
    """Error communicating with Trakt API."""
    pass


class TraktAuthError(TraktError):
    """Trakt authentication failed."""
    pass


class TraktRateLimitError(TraktError):
    """Trakt rate limit exceeded."""
    
    def __init__(self, retry_after: int = 60):
        self.retry_after = retry_after
        super().__init__(f"Rate limited. Retry after {retry_after} seconds.")


class SerializdError(SyncError):
    """Error communicating with Serializd API."""
    pass


class SerializdAuthError(SerializdError):
    """Serializd authentication failed."""
    pass


class SerializdEmptySeasonError(SerializdError):
    """Serializd returned empty season data (likely no episodes)."""
    pass


class ConflictError(SyncError):
    """Conflict detected during sync that couldn't be resolved."""
    pass


class StateError(SyncError):
    """Error with sync state management."""
    pass
