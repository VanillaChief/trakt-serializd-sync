# AI-generated: Configuration loading from ~/keys/ and environment
"""Configuration management for trakt-serializd-sync."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


# Default paths
KEYS_DIR = Path.home() / "keys"
ENV_FILE = KEYS_DIR / "trakt-serializd-sync.env"


def load_config() -> dict[str, Any]:
    """
    Load configuration from environment and ~/keys/trakt-serializd-sync.env.
    
    Priority (highest to lowest):
    1. Environment variables
    2. ~/keys/trakt-serializd-sync.env
    
    Returns:
        Dict with configuration values.
    """
    # Load from ~/keys/ first (will be overridden by actual env vars)
    if ENV_FILE.exists():
        load_dotenv(ENV_FILE)
    
    return {
        # Serializd credentials
        "serializd_email": os.environ.get("SERIALIZD_EMAIL"),
        "serializd_password": os.environ.get("SERIALIZD_PASSWORD"),
        
        # Sync settings
        "sync_interval_minutes": int(os.environ.get("SYNC_INTERVAL_MINUTES", "15")),
        "conflict_strategy": os.environ.get("CONFLICT_STRATEGY", "trakt-wins"),
        "sync_direction": os.environ.get("SYNC_DIRECTION", "both"),
        
        # Rate limiting
        "serializd_delay_ms": int(os.environ.get("SERIALIZD_DELAY_MS", "200")),
        
        # Logging
        "log_level": os.environ.get("LOG_LEVEL", "INFO"),
    }


def get_serializd_credentials() -> tuple[str | None, str | None]:
    """
    Get Serializd email and password from environment.
    
    Loads from ~/keys/trakt-serializd-sync.env if not already in environment.
    
    Returns:
        Tuple of (email, password), either may be None if not configured.
    """
    if ENV_FILE.exists():
        load_dotenv(ENV_FILE)
    
    return (
        os.environ.get("SERIALIZD_EMAIL"),
        os.environ.get("SERIALIZD_PASSWORD"),
    )
