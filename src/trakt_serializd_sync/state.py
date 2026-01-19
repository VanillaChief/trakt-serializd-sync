# AI-generated: Sync state management for bidirectional sync
"""State management for tracking sync progress between platforms."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from platformdirs import user_data_dir

from trakt_serializd_sync.models import WatchActivity


class SyncState:
    """
    Manages sync state between Trakt and Serializd.
    
    Tracks:
    - Last sync timestamps for each platform and direction
    - Activity ledger to detect what's been synced
    - Sync statistics
    """

    def __init__(self, data_dir: Path | None = None):
        self.logger = logging.getLogger(__name__)
        self.data_dir = data_dir or Path(user_data_dir("trakt-serializd-sync"))
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.state_file = self.data_dir / "sync_state.json"
        
        self._state: dict[str, Any] = self._load_state()

    def _load_state(self) -> dict[str, Any]:
        """Load state from disk or return default state."""
        if self.state_file.exists():
            try:
                return json.loads(self.state_file.read_text())
            except (json.JSONDecodeError, KeyError) as e:
                self.logger.warning(f"Failed to load sync state: {e}")
        
        return self._default_state()

    def _default_state(self) -> dict[str, Any]:
        """Return the default empty state."""
        return {
            "version": 1,
            "last_sync": None,
            "trakt": {
                "last_fetched_at": None,
                "last_watched_at": None,
                "last_rated_at": None,
            },
            "serializd": {
                "last_fetched_at": None,
                "last_diary_at": None,
            },
            "synced_activities": [],  # List of activity keys that have been synced
            "excluded_activities": {},  # Dict of activity keys -> exclusion reason
            "stats": {
                "total_syncs": 0,
                "trakt_to_serializd": 0,
                "serializd_to_trakt": 0,
                "conflicts_resolved": 0,
                "errors": 0,
                "excluded": 0,
            },
        }

    def save(self) -> None:
        """Save state to disk."""
        self._state["last_sync"] = datetime.now().isoformat()
        self.state_file.write_text(json.dumps(self._state, indent=2))
        self.logger.debug("Sync state saved")

    def reset(self) -> None:
        """Reset state to defaults."""
        self._state = self._default_state()
        self.save()
        self.logger.info("Sync state reset")

    # === Timestamp Management ===

    @property
    def last_sync(self) -> datetime | None:
        """Get the timestamp of the last sync operation."""
        ts = self._state.get("last_sync")
        return datetime.fromisoformat(ts) if ts else None

    @property
    def trakt_last_fetched(self) -> datetime | None:
        """Get the timestamp of the last Trakt data fetch."""
        ts = self._state.get("trakt", {}).get("last_fetched_at")
        return datetime.fromisoformat(ts) if ts else None

    @trakt_last_fetched.setter
    def trakt_last_fetched(self, value: datetime) -> None:
        self._state.setdefault("trakt", {})["last_fetched_at"] = value.isoformat()

    @property
    def trakt_last_watched(self) -> datetime | None:
        """Get the timestamp of the last Trakt watch activity."""
        ts = self._state.get("trakt", {}).get("last_watched_at")
        return datetime.fromisoformat(ts) if ts else None

    @trakt_last_watched.setter
    def trakt_last_watched(self, value: datetime) -> None:
        self._state.setdefault("trakt", {})["last_watched_at"] = value.isoformat()

    @property
    def serializd_last_fetched(self) -> datetime | None:
        """Get the timestamp of the last Serializd data fetch."""
        ts = self._state.get("serializd", {}).get("last_fetched_at")
        return datetime.fromisoformat(ts) if ts else None

    @serializd_last_fetched.setter
    def serializd_last_fetched(self, value: datetime) -> None:
        self._state.setdefault("serializd", {})["last_fetched_at"] = value.isoformat()

    @property
    def serializd_last_diary(self) -> datetime | None:
        """Get the timestamp of the last Serializd diary entry."""
        ts = self._state.get("serializd", {}).get("last_diary_at")
        return datetime.fromisoformat(ts) if ts else None

    @serializd_last_diary.setter
    def serializd_last_diary(self, value: datetime) -> None:
        self._state.setdefault("serializd", {})["last_diary_at"] = value.isoformat()

    # === Activity Ledger ===

    def is_synced(self, activity: WatchActivity) -> bool:
        """Check if an activity has already been synced or excluded."""
        return (
            activity.key in self._state.get("synced_activities", [])
            or activity.key in self._state.get("excluded_activities", {})
        )

    def is_excluded(self, activity: WatchActivity) -> bool:
        """Check if an activity is permanently excluded from sync."""
        return activity.key in self._state.get("excluded_activities", {})

    def get_exclusion_reason(self, activity: WatchActivity) -> str | None:
        """Get the reason an activity was excluded."""
        return self._state.get("excluded_activities", {}).get(activity.key)

    def mark_synced(self, activity: WatchActivity) -> None:
        """Mark an activity as synced."""
        synced = self._state.setdefault("synced_activities", [])
        if activity.key not in synced:
            synced.append(activity.key)

    def mark_synced_batch(self, activities: list[WatchActivity]) -> None:
        """Mark multiple activities as synced."""
        synced = set(self._state.setdefault("synced_activities", []))
        for activity in activities:
            synced.add(activity.key)
        self._state["synced_activities"] = list(synced)

    def get_unsynced(self, activities: list[WatchActivity]) -> list[WatchActivity]:
        """Filter out already-synced activities."""
        synced = set(self._state.get("synced_activities", []))
        return [a for a in activities if a.key not in synced]

    def clear_synced_activities(self) -> None:
        """Clear the synced activities ledger."""
        self._state["synced_activities"] = []

    # === Exclusion Management ===

    def exclude_activity(
        self,
        activity: WatchActivity,
        reason: str,
    ) -> None:
        """Permanently exclude an activity from sync with a reason."""
        excluded = self._state.setdefault("excluded_activities", {})
        if activity.key not in excluded:
            excluded[activity.key] = reason
            self.increment_stat("excluded")

    def exclude_activities_batch(
        self,
        activities: list[WatchActivity],
        reason: str,
    ) -> None:
        """Exclude multiple activities with the same reason."""
        excluded = self._state.setdefault("excluded_activities", {})
        for activity in activities:
            if activity.key not in excluded:
                excluded[activity.key] = reason
                self.increment_stat("excluded")

    def clear_exclusions(self) -> None:
        """Clear all exclusions (use for retry after platform updates)."""
        self._state["excluded_activities"] = {}

    @property
    def excluded_count(self) -> int:
        """Get the number of excluded activities."""
        return len(self._state.get("excluded_activities", {}))

    def get_exclusion_summary(self) -> dict[str, int]:
        """Get a summary of exclusions by reason."""
        from collections import Counter
        excluded = self._state.get("excluded_activities", {})
        return dict(Counter(excluded.values()))

    @property
    def synced_count(self) -> int:
        """Get the number of synced activities."""
        return len(self._state.get("synced_activities", []))

    # === Statistics ===

    def increment_stat(self, stat: str, amount: int = 1) -> None:
        """Increment a sync statistic."""
        stats = self._state.setdefault("stats", {})
        stats[stat] = stats.get(stat, 0) + amount

    @property
    def stats(self) -> dict[str, int]:
        """Get sync statistics."""
        return self._state.get("stats", {})

    def record_sync(
        self,
        trakt_to_serializd: int = 0,
        serializd_to_trakt: int = 0,
        conflicts: int = 0,
        errors: int = 0,
    ) -> None:
        """Record statistics from a sync operation."""
        self.increment_stat("total_syncs")
        self.increment_stat("trakt_to_serializd", trakt_to_serializd)
        self.increment_stat("serializd_to_trakt", serializd_to_trakt)
        self.increment_stat("conflicts_resolved", conflicts)
        self.increment_stat("errors", errors)

    # === State Info ===

    def get_status(self) -> dict[str, Any]:
        """Get a summary of the current sync state."""
        return {
            "last_sync": self.last_sync.isoformat() if self.last_sync else None,
            "trakt": {
                "last_fetched": (
                    self.trakt_last_fetched.isoformat() if self.trakt_last_fetched else None
                ),
                "last_watched": (
                    self.trakt_last_watched.isoformat() if self.trakt_last_watched else None
                ),
            },
            "serializd": {
                "last_fetched": (
                    self.serializd_last_fetched.isoformat() if self.serializd_last_fetched else None
                ),
                "last_diary": (
                    self.serializd_last_diary.isoformat() if self.serializd_last_diary else None
                ),
            },
            "synced_activities": self.synced_count,
            "excluded_activities": self.excluded_count,
            "exclusion_summary": self.get_exclusion_summary(),
            "stats": self.stats,
        }
