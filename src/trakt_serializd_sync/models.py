# AI-generated: Pydantic models for API requests and responses
"""Data models for Trakt and Serializd API interactions."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# === Sync Direction and Conflict Resolution ===

class SyncDirection(str, Enum):
    """Direction of sync operation."""
    BOTH = "both"
    TRAKT_TO_SERIALIZD = "trakt-to-serializd"
    SERIALIZD_TO_TRAKT = "serializd-to-trakt"


class ConflictStrategy(str, Enum):
    """Strategy for resolving conflicts between platforms."""
    TRAKT_WINS = "trakt-wins"
    SERIALIZD_WINS = "serializd-wins"
    NEWEST_WINS = "newest-wins"


# === Activity Models (Platform-agnostic) ===

class WatchActivity(BaseModel):
    """Represents a single watch event that can be synced between platforms."""
    tmdb_show_id: int
    season_number: int
    episode_number: int
    watched_at: datetime
    is_rewatch: bool = False
    rating: int | None = None  # 1-10 scale (None = no rating)
    source: str  # "trakt" or "serializd"
    
    @property
    def key(self) -> str:
        """Unique key for deduplication (show:season:episode:date)."""
        date_str = self.watched_at.strftime("%Y-%m-%d")
        return f"{self.tmdb_show_id}:{self.season_number}:{self.episode_number}:{date_str}"
    
    def __hash__(self):
        return hash(self.key)
    
    def __eq__(self, other):
        if not isinstance(other, WatchActivity):
            return False
        return self.key == other.key


# === Serializd API Models ===

class SerializdLoginRequest(BaseModel):
    """Request to log in to Serializd."""
    email: str
    password: str


class SerializdLoginResponse(BaseModel):
    """Response from Serializd login."""
    token: str
    user: dict[str, Any] = Field(default_factory=dict)


class SerializdLogEpisodesRequest(BaseModel):
    """Request to mark episodes as watched on Serializd."""
    episode_numbers: list[int]
    season_id: int
    show_id: int
    should_get_next_episode: bool = False


class SerializdUnlogEpisodesRequest(BaseModel):
    """Request to unmark episodes as watched on Serializd."""
    episode_numbers: list[int]
    season_id: int
    show_id: int


class SerializdDiaryEntryRequest(BaseModel):
    """Request to add an episode to Serializd diary with a specific date."""
    show_id: int
    season_id: int
    episode_number: int
    backdate: str = Field(
        ...,
        description="ISO 8601 datetime string (e.g., '2025-06-15T12:00:00Z')"
    )
    review_text: str = ""
    rating: int = Field(default=0, ge=0, le=10)
    contains_spoiler: bool = False
    is_log: bool = True
    is_rewatch: bool = False
    tags: list[str] = Field(default_factory=list)
    allows_comments: bool = True
    like: bool = False
    
    @classmethod
    def from_activity(
        cls,
        activity: WatchActivity,
        season_id: int,
    ) -> SerializdDiaryEntryRequest:
        """Create diary entry request from a WatchActivity."""
        # Convert rating from 1-10 to 0-10 (0 = no rating)
        rating = activity.rating if activity.rating is not None else 0
        
        return cls(
            show_id=activity.tmdb_show_id,
            season_id=season_id,
            episode_number=activity.episode_number,
            backdate=activity.watched_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
            is_rewatch=activity.is_rewatch,
            rating=rating,
        )


class SerializdSeasonInfo(BaseModel):
    """Season information from Serializd."""
    model_config = {"populate_by_name": True}
    
    season_id: int = Field(alias="seasonId")
    season_number: int = Field(alias="seasonNumber")
    episode_count: int = Field(alias="episodeCount", default=0)


class SerializdDiaryEntry(BaseModel):
    """A diary entry from Serializd."""
    model_config = {"populate_by_name": True}
    
    id: int
    show_id: int = Field(alias="showId")
    season_id: int = Field(alias="seasonId")
    season_number: int = Field(alias="seasonNumber")
    episode_number: int = Field(alias="episodeNumber")
    rating: int = 0
    review_text: str = Field(alias="reviewText", default="")
    is_rewatch: bool = Field(alias="isRewatch", default=False)
    date_added: datetime = Field(alias="dateAdded")
    backdate: datetime | None = None
    
    def to_activity(self) -> WatchActivity:
        """Convert to a WatchActivity for syncing."""
        # Use backdate if available, otherwise dateAdded
        watched_at = self.backdate or self.date_added
        # Convert rating from 0-10 to 1-10 (0 becomes None)
        rating = self.rating if self.rating > 0 else None
        
        return WatchActivity(
            tmdb_show_id=self.show_id,
            season_number=self.season_number,
            episode_number=self.episode_number,
            watched_at=watched_at,
            is_rewatch=self.is_rewatch,
            rating=rating,
            source="serializd",
        )


# === Trakt API Models ===

class TraktSyncHistoryRequest(BaseModel):
    """Request to add items to Trakt watch history."""
    shows: list[dict[str, Any]] = Field(default_factory=list)
    
    @classmethod
    def from_activities(cls, activities: list[WatchActivity]) -> TraktSyncHistoryRequest:
        """Create a sync request from a list of WatchActivities."""
        # Group by show
        shows_map: dict[int, dict[str, Any]] = {}
        
        for activity in activities:
            show_id = activity.tmdb_show_id
            if show_id not in shows_map:
                shows_map[show_id] = {
                    "ids": {"tmdb": show_id},
                    "seasons": {},
                }
            
            season_num = activity.season_number
            if season_num not in shows_map[show_id]["seasons"]:
                shows_map[show_id]["seasons"][season_num] = {
                    "number": season_num,
                    "episodes": [],
                }
            
            shows_map[show_id]["seasons"][season_num]["episodes"].append({
                "number": activity.episode_number,
                "watched_at": activity.watched_at.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            })
        
        # Convert seasons dict to list
        shows = []
        for show_data in shows_map.values():
            show_data["seasons"] = list(show_data["seasons"].values())
            shows.append(show_data)
        
        return cls(shows=shows)


class TraktSyncRatingsRequest(BaseModel):
    """Request to add ratings to Trakt."""
    shows: list[dict[str, Any]] = Field(default_factory=list)
    episodes: list[dict[str, Any]] = Field(default_factory=list)


class TraktHistoryEntry(BaseModel):
    """A history entry from Trakt."""
    id: int
    watched_at: datetime
    action: str = "watch"
    type: str = "episode"
    episode: dict[str, Any] = Field(default_factory=dict)
    show: dict[str, Any] = Field(default_factory=dict)
    
    def to_activity(self) -> WatchActivity | None:
        """Convert to a WatchActivity for syncing."""
        show_ids = self.show.get("ids", {})
        tmdb_id = show_ids.get("tmdb")
        
        if not tmdb_id:
            return None
        
        season_num = self.episode.get("season")
        episode_num = self.episode.get("number")
        
        if season_num is None or episode_num is None:
            return None
        
        return WatchActivity(
            tmdb_show_id=tmdb_id,
            season_number=season_num,
            episode_number=episode_num,
            watched_at=self.watched_at,
            is_rewatch=False,  # Determined during sync by checking existing entries
            rating=None,  # Ratings fetched separately
            source="trakt",
        )


class TraktLastActivities(BaseModel):
    """Timestamps of last activities on Trakt."""
    all: datetime
    movies: dict[str, datetime] = Field(default_factory=dict)
    episodes: dict[str, datetime] = Field(default_factory=dict)
    shows: dict[str, datetime] = Field(default_factory=dict)
    seasons: dict[str, datetime] = Field(default_factory=dict)
    
    @property
    def last_watched_at(self) -> datetime | None:
        """Get the timestamp of the last episode watch."""
        return self.episodes.get("watched_at")
    
    @property
    def last_rated_at(self) -> datetime | None:
        """Get the timestamp of the last episode rating."""
        return self.episodes.get("rated_at")
