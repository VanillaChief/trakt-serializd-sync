"""API clients for Trakt and Serializd."""

from trakt_serializd_sync.clients.serializd import SerializdClient
from trakt_serializd_sync.clients.trakt import TraktClient

__all__ = ["TraktClient", "SerializdClient"]
