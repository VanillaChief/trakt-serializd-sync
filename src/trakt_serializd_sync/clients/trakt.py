# AI-generated: Trakt API client with bidirectional sync support
"""Trakt API client for authentication and data sync."""

import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
from platformdirs import user_data_dir

from trakt_serializd_sync.consts import (
    TRAKT_BASE_URL,
    TRAKT_CLIENT_ID,
    TRAKT_CLIENT_SECRET,
    TRAKT_REDIRECT_URI,
)
from trakt_serializd_sync.exceptions import TraktAuthError, TraktError, TraktRateLimitError
from trakt_serializd_sync.models import (
    TraktHistoryEntry,
    TraktLastActivities,
    TraktSyncHistoryRequest,
    WatchActivity,
)


class TraktClient:
    """Client for Trakt API with OAuth device flow authentication."""

    def __init__(self, data_dir: Path | None = None):
        self.logger = logging.getLogger(__name__)
        self.data_dir = data_dir or Path(user_data_dir("trakt-serializd-sync"))
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.token_file = self.data_dir / "trakt_token.json"
        
        self.session = httpx.Client(base_url=TRAKT_BASE_URL, timeout=30.0)
        self.session.headers.update({
            'Content-Type': 'application/json',
            'trakt-api-key': TRAKT_CLIENT_ID,
            'trakt-api-version': '2',
        })
        
        self._username: str | None = None

    def load_saved_token(self) -> bool:
        """Load saved token from disk. Returns True if successful."""
        if not self.token_file.exists():
            return False
        
        try:
            token_data = json.loads(self.token_file.read_text())
            access_token = token_data.get("access_token")
            
            if not access_token:
                return False
            
            # Check if token is expired
            expires_at = token_data.get("expires_at", 0)
            if time.time() >= expires_at:
                self.logger.info("Trakt token expired, attempting refresh...")
                refresh_token = token_data.get("refresh_token")
                if refresh_token:
                    try:
                        self.refresh_token(refresh_token)
                        return True
                    except TraktError:
                        return False
                return False
            
            self.session.headers["Authorization"] = f"Bearer {access_token}"
            return True
        except (json.JSONDecodeError, KeyError) as e:
            self.logger.warning(f"Failed to load Trakt token: {e}")
            return False

    def save_token(self, token_data: dict[str, Any]) -> None:
        """Save token data to disk."""
        # Calculate expiration timestamp
        if "expires_in" in token_data and "expires_at" not in token_data:
            token_data["expires_at"] = int(time.time()) + token_data["expires_in"]
        
        self.token_file.write_text(json.dumps(token_data, indent=2))
        self.logger.info("Trakt token saved")

    def login(self) -> dict[str, Any]:
        """
        Perform OAuth device flow login.
        
        This is interactive - the user must visit a URL and enter a code.
        
        Returns:
            Token data with access_token, refresh_token, etc.
        
        Raises:
            TraktAuthError: If login fails or times out.
        """
        resp = self.session.post(
            '/oauth/device/code',
            json={'client_id': TRAKT_CLIENT_ID}
        )
        
        if not resp.is_success:
            raise TraktAuthError(f"Failed to get device code: {resp.status_code}")
        
        code_data = resp.json()
        verification_url = code_data['verification_url']
        user_code = code_data['user_code']
        device_code = code_data['device_code']
        interval = code_data.get('interval', 5)
        expires_in = code_data.get('expires_in', 600)
        
        self.logger.info(f"Open {verification_url} and enter code: {user_code}")
        print(f"\n🔗 Open: {verification_url}")
        print(f"📝 Enter code: {user_code}\n")
        
        expiry = int(time.time()) + expires_in
        
        while int(time.time()) < expiry:
            time.sleep(interval)
            
            auth_resp = self.session.post(
                '/oauth/device/token',
                json={
                    'code': device_code,
                    'client_id': TRAKT_CLIENT_ID,
                    'client_secret': TRAKT_CLIENT_SECRET,
                }
            )
            
            if auth_resp.status_code == 200:
                token_data = auth_resp.json()
                self.session.headers["Authorization"] = f"Bearer {token_data['access_token']}"
                self.save_token(token_data)
                return token_data
            elif auth_resp.status_code == 400:
                # Still waiting for user authorization
                continue
            elif auth_resp.status_code == 404:
                raise TraktAuthError("Invalid device code")
            elif auth_resp.status_code == 409:
                raise TraktAuthError("Code already used")
            elif auth_resp.status_code == 410:
                raise TraktAuthError("Code expired")
            elif auth_resp.status_code == 418:
                raise TraktAuthError("User denied authorization")
            elif auth_resp.status_code == 429:
                # Slow down polling
                interval = min(interval + 1, 30)
        
        raise TraktAuthError("Authorization timed out")

    def refresh_token(self, refresh_token: str) -> dict[str, Any]:
        """
        Refresh the access token using a refresh token.
        
        Args:
            refresh_token: The refresh token from previous auth.
        
        Returns:
            New token data.
        
        Raises:
            TraktAuthError: If refresh fails.
        """
        resp = self.session.post(
            '/oauth/token',
            json={
                'refresh_token': refresh_token,
                'client_id': TRAKT_CLIENT_ID,
                'client_secret': TRAKT_CLIENT_SECRET,
                'redirect_uri': TRAKT_REDIRECT_URI,
                'grant_type': 'refresh_token',
            }
        )
        
        if not resp.is_success:
            raise TraktAuthError(f"Token refresh failed: {resp.status_code}")
        
        token_data = resp.json()
        self.session.headers["Authorization"] = f"Bearer {token_data['access_token']}"
        self.save_token(token_data)
        return token_data

    @property
    def username(self) -> str:
        """Get the authenticated user's username."""
        if self._username is None:
            user_info = self.get_user_info()
            self._username = user_info.get("user", {}).get("username", "me")
        return self._username

    def get_user_info(self) -> dict[str, Any]:
        """Get info about the authenticated user."""
        resp = self.session.get('/users/settings')
        
        if resp.status_code == 401:
            raise TraktAuthError("Not authenticated")
        
        if not resp.is_success:
            raise TraktError(f"Failed to get user info: {resp.status_code}")
        
        return resp.json()

    def get_last_activities(self) -> TraktLastActivities:
        """
        Get timestamps of the user's last activities.
        
        Useful for incremental sync - only fetch history newer than last sync.
        """
        resp = self.session.get('/sync/last-activities')
        
        if resp.status_code == 401:
            raise TraktAuthError("Not authenticated")
        
        if not resp.is_success:
            raise TraktError(f"Failed to get last activities: {resp.status_code}")
        
        data = resp.json()
        return TraktLastActivities(**data)

    def get_episode_history(
        self,
        since: datetime | None = None,
        limit: int | None = None,
    ) -> list[TraktHistoryEntry]:
        """
        Fetch episode watch history, optionally filtered by time.
        
        Args:
            since: Only fetch history after this timestamp.
            limit: Maximum number of entries (None = all).
        
        Returns:
            List of history entries, newest first.
        """
        all_history: list[TraktHistoryEntry] = []
        page = 1
        per_page = 1000
        
        params: dict[str, Any] = {'limit': per_page}
        if since:
            params['start_at'] = since.strftime("%Y-%m-%dT%H:%M:%S.000Z")
        
        while True:
            params['page'] = page
            resp = self.session.get(f'/users/{self.username}/history/episodes', params=params)
            
            self._check_rate_limit(resp)
            
            if not resp.is_success:
                raise TraktError(f"Failed to fetch history: {resp.status_code}")
            
            batch = resp.json()
            if not batch:
                break
            
            for entry in batch:
                all_history.append(TraktHistoryEntry(**entry))
            
            self.logger.debug(f"Fetched {len(all_history)} history entries...")
            
            if limit and len(all_history) >= limit:
                all_history = all_history[:limit]
                break
            
            # Check pagination
            total_pages = int(resp.headers.get('x-pagination-page-count', 1))
            if page >= total_pages:
                break
            page += 1
        
        return all_history

    def get_episode_ratings(self) -> dict[str, int]:
        """
        Fetch all episode ratings.
        
        Returns:
            Dict mapping "show_tmdb:season:episode" to rating (1-10).
        """
        resp = self.session.get('/sync/ratings/episodes')
        
        self._check_rate_limit(resp)
        
        if not resp.is_success:
            raise TraktError(f"Failed to fetch ratings: {resp.status_code}")
        
        ratings: dict[str, int] = {}
        for entry in resp.json():
            show = entry.get("show", {})
            episode = entry.get("episode", {})
            rating = entry.get("rating")
            
            tmdb_id = show.get("ids", {}).get("tmdb")
            season = episode.get("season")
            ep_num = episode.get("number")
            
            if all([tmdb_id, season is not None, ep_num, rating]):
                key = f"{tmdb_id}:{season}:{ep_num}"
                ratings[key] = rating
        
        return ratings

    def add_to_history(self, activities: list[WatchActivity]) -> dict[str, Any]:
        """
        Add watch activities to Trakt history.
        
        Args:
            activities: List of watch activities to add.
        
        Returns:
            Response with added/not_found counts.
        """
        if not activities:
            return {"added": {"episodes": 0}, "not_found": {"shows": []}}
        
        request = TraktSyncHistoryRequest.from_activities(activities)
        
        resp = self.session.post(
            '/sync/history',
            json=request.model_dump(),
        )
        
        self._check_rate_limit(resp)
        
        if not resp.is_success:
            raise TraktError(f"Failed to add history: {resp.status_code}")
        
        return resp.json()

    def add_rating(
        self,
        tmdb_show_id: int,
        season: int,
        episode: int,
        rating: int,
        rated_at: datetime | None = None,
    ) -> bool:
        """
        Add a rating for an episode.
        
        Args:
            tmdb_show_id: TMDB show ID.
            season: Season number.
            episode: Episode number.
            rating: Rating value (1-10).
            rated_at: When the rating was made (optional).
        
        Returns:
            True if successful.
        """
        if not 1 <= rating <= 10:
            self.logger.warning(f"Invalid rating {rating}, must be 1-10")
            return False
        
        episode_data: dict[str, Any] = {
            "ids": {"tmdb": tmdb_show_id},
            "seasons": [{
                "number": season,
                "episodes": [{
                    "number": episode,
                    "rating": rating,
                }]
            }]
        }
        
        if rated_at:
            episode_data["seasons"][0]["episodes"][0]["rated_at"] = (
                rated_at.strftime("%Y-%m-%dT%H:%M:%S.000Z")
            )
        
        resp = self.session.post(
            '/sync/ratings',
            json={"shows": [episode_data]},
        )
        
        self._check_rate_limit(resp)
        
        if not resp.is_success:
            self.logger.error(f"Failed to add rating: {resp.status_code}")
            return False
        
        return True

    def _check_rate_limit(self, resp: httpx.Response) -> None:
        """Check response for rate limit headers and raise if exceeded."""
        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", 60))
            raise TraktRateLimitError(retry_after)
        
        # Log remaining calls
        remaining = resp.headers.get("X-Ratelimit-Remaining")
        if remaining and int(remaining) < 100:
            self.logger.warning(f"Trakt rate limit: {remaining} calls remaining")
