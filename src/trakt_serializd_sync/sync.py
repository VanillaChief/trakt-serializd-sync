# AI-generated: Core sync engine with conflict resolution
"""Sync engine for bidirectional sync between Trakt and Serializd."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Callable

from trakt_serializd_sync.clients import SerializdClient, TraktClient
from trakt_serializd_sync.exceptions import SyncError
from trakt_serializd_sync.models import ConflictStrategy, SyncDirection, WatchActivity
from trakt_serializd_sync.retry import retry_with_backoff
from trakt_serializd_sync.state import SyncState


class SyncEngine:
    """
    Bidirectional sync engine for Trakt and Serializd.
    
    Handles:
    - Fetching activities from both platforms
    - Detecting new/changed activities
    - Resolving conflicts based on strategy
    - Pushing changes to each platform
    """

    def __init__(
        self,
        trakt: TraktClient,
        serializd: SerializdClient,
        state: SyncState,
        conflict_strategy: ConflictStrategy = ConflictStrategy.TRAKT_WINS,
        dry_run: bool = False,
        progress_callback: Callable[[str], None] | None = None,
    ):
        self.logger = logging.getLogger(__name__)
        self.trakt = trakt
        self.serializd = serializd
        self.state = state
        self.conflict_strategy = conflict_strategy
        self.dry_run = dry_run
        self.progress = progress_callback or (lambda msg: None)

    def sync(self, direction: SyncDirection = SyncDirection.BOTH) -> dict[str, int]:
        """
        Perform a sync operation.
        
        Args:
            direction: Which direction(s) to sync.
        
        Returns:
            Dict with counts of synced items per direction.
        """
        results = {
            "trakt_to_serializd": 0,
            "serializd_to_trakt": 0,
            "conflicts": 0,
            "errors": 0,
            "excluded": 0,
        }
        
        try:
            # Fetch activities from both platforms
            self.progress("Fetching activities from Trakt...")
            trakt_activities = self._fetch_trakt_activities()
            self.logger.info(f"Found {len(trakt_activities)} activities on Trakt")
            
            self.progress("Fetching activities from Serializd...")
            serializd_activities = self._fetch_serializd_activities()
            self.logger.info(f"Found {len(serializd_activities)} activities on Serializd")
            
            # Build activity maps for conflict detection
            trakt_map = {a.key: a for a in trakt_activities}
            serializd_map = {a.key: a for a in serializd_activities}
            
            # Find activities to sync in each direction
            to_serializd: list[WatchActivity] = []
            to_trakt: list[WatchActivity] = []
            
            if direction in (SyncDirection.BOTH, SyncDirection.TRAKT_TO_SERIALIZD):
                # Find Trakt activities not in Serializd
                for key, activity in trakt_map.items():
                    if key not in serializd_map and not self.state.is_synced(activity):
                        to_serializd.append(activity)
            
            if direction in (SyncDirection.BOTH, SyncDirection.SERIALIZD_TO_TRAKT):
                # Find Serializd activities not in Trakt
                for key, activity in serializd_map.items():
                    if key not in trakt_map and not self.state.is_synced(activity):
                        to_trakt.append(activity)
            
            # Handle conflicts (same episode, different data)
            if direction == SyncDirection.BOTH:
                conflicts = self._detect_conflicts(trakt_map, serializd_map)
                if conflicts:
                    self.logger.info(f"Found {len(conflicts)} conflicts to resolve")
                    resolved_to_serializd, resolved_to_trakt = self._resolve_conflicts(conflicts)
                    to_serializd.extend(resolved_to_serializd)
                    to_trakt.extend(resolved_to_trakt)
                    results["conflicts"] = len(conflicts)
            
            # Perform syncs
            if to_serializd:
                self.progress(f"Syncing {len(to_serializd)} activities to Serializd...")
                synced = self._sync_to_serializd(to_serializd)
                results["trakt_to_serializd"] = synced
            
            if to_trakt:
                self.progress(f"Syncing {len(to_trakt)} activities to Trakt...")
                synced = self._sync_to_trakt(to_trakt)
                results["serializd_to_trakt"] = synced
            
            # Update state
            self.state.record_sync(
                trakt_to_serializd=results["trakt_to_serializd"],
                serializd_to_trakt=results["serializd_to_trakt"],
                conflicts=results["conflicts"],
                errors=results["errors"],
            )
            self.state.save()
            
            self.progress("Sync complete!")
            return results
            
        except Exception as e:
            self.logger.error(f"Sync failed: {e}")
            results["errors"] += 1
            self.state.increment_stat("errors")
            self.state.save()
            raise SyncError(f"Sync failed: {e}") from e

    @retry_with_backoff(max_retries=3)
    def _fetch_trakt_activities(self) -> list[WatchActivity]:
        """Fetch watch activities from Trakt."""
        # Use incremental fetch if we have a previous sync timestamp
        since = self.state.trakt_last_watched
        
        history = self.trakt.get_episode_history(since=since)
        
        # Get ratings to enrich activities
        ratings = self.trakt.get_episode_ratings()
        
        activities: list[WatchActivity] = []
        for entry in history:
            activity = entry.to_activity()
            if activity:
                # Add rating if available
                rating_key = f"{activity.tmdb_show_id}:{activity.season_number}:{activity.episode_number}"
                if rating_key in ratings:
                    activity.rating = ratings[rating_key]
                activities.append(activity)
        
        # Update state with latest timestamp
        if history:
            latest = max(h.watched_at for h in history)
            self.state.trakt_last_watched = latest
            self.state.trakt_last_fetched = datetime.now()
        
        return activities

    @retry_with_backoff(max_retries=3)
    def _fetch_serializd_activities(self) -> list[WatchActivity]:
        """Fetch watch activities from Serializd diary."""
        # Use incremental fetch if we have a previous sync timestamp
        since = self.state.serializd_last_diary
        
        entries = self.serializd.get_diary_entries(since=since)
        
        activities: list[WatchActivity] = []
        for entry in entries:
            try:
                activity = entry.to_activity()
                activities.append(activity)
            except Exception as e:
                self.logger.warning(f"Failed to convert diary entry: {e}")
        
        # Update state with latest timestamp
        if entries:
            latest = max(e.date_added for e in entries)
            self.state.serializd_last_diary = latest
            self.state.serializd_last_fetched = datetime.now()
        
        return activities

    def _detect_conflicts(
        self,
        trakt_map: dict[str, WatchActivity],
        serializd_map: dict[str, WatchActivity],
    ) -> list[tuple[WatchActivity, WatchActivity]]:
        """
        Find activities that exist on both platforms with different data.
        
        A conflict occurs when the same episode was watched on the same day
        but has different ratings.
        """
        conflicts: list[tuple[WatchActivity, WatchActivity]] = []
        
        common_keys = set(trakt_map.keys()) & set(serializd_map.keys())
        
        for key in common_keys:
            trakt_activity = trakt_map[key]
            serializd_activity = serializd_map[key]
            
            # Check for rating conflict
            if trakt_activity.rating != serializd_activity.rating:
                # Only if both have ratings
                if trakt_activity.rating is not None and serializd_activity.rating is not None:
                    conflicts.append((trakt_activity, serializd_activity))
        
        return conflicts

    def _resolve_conflicts(
        self,
        conflicts: list[tuple[WatchActivity, WatchActivity]],
    ) -> tuple[list[WatchActivity], list[WatchActivity]]:
        """
        Resolve conflicts based on the configured strategy.
        
        Returns:
            Tuple of (activities to sync to Serializd, activities to sync to Trakt)
        """
        to_serializd: list[WatchActivity] = []
        to_trakt: list[WatchActivity] = []
        
        for trakt_activity, serializd_activity in conflicts:
            if self.conflict_strategy == ConflictStrategy.TRAKT_WINS:
                # Push Trakt version to Serializd
                to_serializd.append(trakt_activity)
                self.logger.debug(
                    f"Conflict: {trakt_activity.key} - Trakt wins "
                    f"(rating {trakt_activity.rating} vs {serializd_activity.rating})"
                )
            
            elif self.conflict_strategy == ConflictStrategy.SERIALIZD_WINS:
                # Push Serializd version to Trakt
                to_trakt.append(serializd_activity)
                self.logger.debug(
                    f"Conflict: {serializd_activity.key} - Serializd wins "
                    f"(rating {serializd_activity.rating} vs {trakt_activity.rating})"
                )
            
            elif self.conflict_strategy == ConflictStrategy.NEWEST_WINS:
                # Compare timestamps
                if trakt_activity.watched_at >= serializd_activity.watched_at:
                    to_serializd.append(trakt_activity)
                    self.logger.debug(f"Conflict: {trakt_activity.key} - Trakt is newer")
                else:
                    to_trakt.append(serializd_activity)
                    self.logger.debug(f"Conflict: {serializd_activity.key} - Serializd is newer")
        
        return to_serializd, to_trakt

    def _sync_to_serializd(self, activities: list[WatchActivity]) -> int:
        """Sync activities to Serializd. Returns count of successfully synced."""
        if self.dry_run:
            self.logger.info(f"[DRY RUN] Would sync {len(activities)} to Serializd")
            return 0
        
        synced = 0
        excluded = 0
        failed = 0
        
        # Group activities by show/season for efficient availability checking
        # and to batch-exclude all episodes from unavailable seasons
        from collections import defaultdict
        by_season: dict[tuple[int, int], list[WatchActivity]] = defaultdict(list)
        no_tmdb: list[WatchActivity] = []
        
        for activity in activities:
            if activity.tmdb_show_id is None:
                no_tmdb.append(activity)
            else:
                key = (activity.tmdb_show_id, activity.season_number)
                by_season[key].append(activity)
        
        # Exclude activities with no TMDB ID
        if no_tmdb:
            self.logger.warning(
                f"⏭️  Excluding {len(no_tmdb)} episodes: no TMDB ID (can't sync to Serializd)"
            )
            self.state.exclude_activities_batch(no_tmdb, "no_tmdb_id")
            excluded += len(no_tmdb)
        
        # Check season availability and sync
        for (show_id, season_num), season_activities in by_season.items():
            # Check availability once per season
            is_available, exclusion_reason, _season_id = (
                self.serializd.check_season_availability(show_id, season_num)
            )
            
            if not is_available and exclusion_reason:
                # Permanent exclusion - batch exclude all episodes from this season
                self.logger.info(
                    f"⏭️  Excluding {len(season_activities)} episodes from "
                    f"show {show_id} S{season_num:02d}: {exclusion_reason}"
                )
                self.state.exclude_activities_batch(season_activities, exclusion_reason)
                excluded += len(season_activities)
                continue
            
            if not is_available:
                # Transient error - mark as failed but don't exclude
                self.logger.warning(
                    f"⚠️  Skipping {len(season_activities)} episodes from "
                    f"show {show_id} S{season_num:02d}: transient error"
                )
                failed += len(season_activities)
                continue
            
            # Season is available - sync each episode
            for activity in season_activities:
                try:
                    success = self.serializd.add_diary_entry(activity)
                    if success:
                        self.state.mark_synced(activity)
                        synced += 1
                        self.logger.debug(
                            f"Synced to Serializd: {activity.tmdb_show_id} "
                            f"S{activity.season_number:02d}E{activity.episode_number:02d}"
                        )
                    else:
                        # API returned failure but no exception
                        failed += 1
                        self.logger.warning(
                            f"⚠️  Failed to sync to Serializd (API rejected): "
                            f"show={activity.tmdb_show_id} S{activity.season_number:02d}E{activity.episode_number:02d} "
                            f"({activity.watched_at.strftime('%Y-%m-%d')})"
                        )
                        # Mark as synced to avoid retrying forever
                        self.state.mark_synced(activity)
                except Exception as e:
                    failed += 1
                    error_msg = str(e)
                    # Provide informative error context
                    self.logger.warning(
                        f"⚠️  Failed to sync to Serializd: "
                        f"show={activity.tmdb_show_id} S{activity.season_number:02d}E{activity.episode_number:02d} "
                        f"({activity.watched_at.strftime('%Y-%m-%d')}) - {error_msg}"
                    )
                    # Mark as synced anyway to avoid retrying forever
                    self.state.mark_synced(activity)
        
        if excluded > 0:
            self.logger.info(
                f"Serializd sync: {synced} synced, {excluded} excluded (incompatible), {failed} failed"
            )
        elif failed > 0:
            self.logger.info(f"Serializd sync: {synced} succeeded, {failed} failed (marked as synced)")
        
        return synced

    def _sync_to_trakt(self, activities: list[WatchActivity]) -> int:
        """Sync activities to Trakt. Returns count of successfully synced."""
        if self.dry_run:
            self.logger.info(f"[DRY RUN] Would sync {len(activities)} to Trakt")
            return 0
        
        if not activities:
            return 0
        
        added = 0
        failed_ratings = 0
        
        try:
            # Batch add to history
            result = self.trakt.add_to_history(activities)
            added = result.get("added", {}).get("episodes", 0)
            not_found = result.get("not_found", {}).get("episodes", [])
            
            if not_found:
                self.logger.warning(
                    f"⚠️  Trakt couldn't find {len(not_found)} episodes - "
                    f"possibly missing from TMDB or wrong IDs"
                )
                for ep in not_found[:5]:  # Show first 5
                    ids = ep.get("ids", {})
                    self.logger.warning(f"    Not found: {ids}")
            
            # Mark all as synced (even not_found to avoid retrying forever)
            self.state.mark_synced_batch(activities)
            
        except Exception as e:
            self.logger.warning(
                f"⚠️  Failed to batch sync {len(activities)} episodes to Trakt: {e}"
            )
            # Mark all as synced anyway to avoid retrying forever
            self.state.mark_synced_batch(activities)
            return 0
        
        # Sync ratings separately with individual error handling
        for activity in activities:
            if activity.rating is not None:
                try:
                    self.trakt.add_rating(
                        tmdb_show_id=activity.tmdb_show_id,
                        season=activity.season_number,
                        episode=activity.episode_number,
                        rating=activity.rating,
                    )
                except Exception as e:
                    failed_ratings += 1
                    self.logger.warning(
                        f"⚠️  Failed to sync rating to Trakt: "
                        f"show={activity.tmdb_show_id} S{activity.season_number:02d}E{activity.episode_number:02d} "
                        f"rating={activity.rating} - {e}"
                    )
        
        if failed_ratings > 0:
            self.logger.info(f"Trakt ratings: {failed_ratings} failed to sync")
        
        self.logger.info(f"Synced {added} episodes to Trakt")
        return added
