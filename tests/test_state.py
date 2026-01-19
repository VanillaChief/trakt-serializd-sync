# AI-generated: Basic tests for sync state management
"""Tests for sync state management."""

import json
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from trakt_serializd_sync.models import WatchActivity
from trakt_serializd_sync.state import SyncState


@pytest.fixture
def temp_data_dir():
    """Create a temporary data directory."""
    with TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def state(temp_data_dir):
    """Create a SyncState with temporary directory."""
    return SyncState(data_dir=temp_data_dir)


@pytest.fixture
def sample_activity():
    """Create a sample watch activity."""
    return WatchActivity(
        tmdb_show_id=12345,
        season_number=1,
        episode_number=5,
        watched_at=datetime(2025, 1, 15, 12, 0, 0),
        is_rewatch=False,
        rating=8,
        source="trakt",
    )


class TestSyncState:
    def test_initial_state(self, state):
        """Test initial state is empty."""
        assert state.last_sync is None
        assert state.trakt_last_fetched is None
        assert state.serializd_last_fetched is None
        assert state.synced_count == 0

    def test_save_and_load(self, temp_data_dir):
        """Test saving and loading state."""
        state1 = SyncState(data_dir=temp_data_dir)
        state1.trakt_last_fetched = datetime(2025, 1, 15, 12, 0, 0)
        state1.save()
        
        # Load in new instance
        state2 = SyncState(data_dir=temp_data_dir)
        assert state2.trakt_last_fetched == datetime(2025, 1, 15, 12, 0, 0)

    def test_mark_synced(self, state, sample_activity):
        """Test marking activity as synced."""
        assert not state.is_synced(sample_activity)
        
        state.mark_synced(sample_activity)
        
        assert state.is_synced(sample_activity)
        assert state.synced_count == 1

    def test_mark_synced_batch(self, state):
        """Test marking multiple activities as synced."""
        activities = [
            WatchActivity(
                tmdb_show_id=12345,
                season_number=1,
                episode_number=i,
                watched_at=datetime(2025, 1, 15, 12, 0, 0),
                source="trakt",
            )
            for i in range(1, 6)
        ]
        
        state.mark_synced_batch(activities)
        
        assert state.synced_count == 5
        for activity in activities:
            assert state.is_synced(activity)

    def test_get_unsynced(self, state, sample_activity):
        """Test filtering unsynced activities."""
        activities = [
            sample_activity,
            WatchActivity(
                tmdb_show_id=12345,
                season_number=1,
                episode_number=6,
                watched_at=datetime(2025, 1, 16, 12, 0, 0),
                source="trakt",
            ),
        ]
        
        state.mark_synced(sample_activity)
        
        unsynced = state.get_unsynced(activities)
        
        assert len(unsynced) == 1
        assert unsynced[0].episode_number == 6

    def test_reset(self, state, sample_activity):
        """Test resetting state."""
        state.mark_synced(sample_activity)
        state.trakt_last_fetched = datetime.now()
        state.save()
        
        state.reset()
        
        assert state.synced_count == 0
        assert state.trakt_last_fetched is None

    def test_statistics(self, state):
        """Test recording statistics."""
        state.record_sync(
            trakt_to_serializd=5,
            serializd_to_trakt=3,
            conflicts=1,
            errors=0,
        )
        
        stats = state.stats
        assert stats['total_syncs'] == 1
        assert stats['trakt_to_serializd'] == 5
        assert stats['serializd_to_trakt'] == 3
        assert stats['conflicts_resolved'] == 1

    def test_get_status(self, state, sample_activity):
        """Test getting status summary."""
        state.mark_synced(sample_activity)
        state.trakt_last_fetched = datetime(2025, 1, 15, 12, 0, 0)
        
        status = state.get_status()
        
        assert status['synced_activities'] == 1
        assert status['trakt']['last_fetched'] is not None


class TestWatchActivity:
    def test_key_generation(self, sample_activity):
        """Test activity key generation."""
        assert sample_activity.key == "12345:1:5:2025-01-15"

    def test_equality(self):
        """Test activity equality based on key."""
        a1 = WatchActivity(
            tmdb_show_id=12345,
            season_number=1,
            episode_number=5,
            watched_at=datetime(2025, 1, 15, 10, 0, 0),
            source="trakt",
        )
        a2 = WatchActivity(
            tmdb_show_id=12345,
            season_number=1,
            episode_number=5,
            watched_at=datetime(2025, 1, 15, 23, 59, 59),
            source="serializd",
        )
        
        # Same day = same key = equal
        assert a1.key == a2.key
        assert a1 == a2

    def test_different_days(self):
        """Test activities on different days are not equal."""
        a1 = WatchActivity(
            tmdb_show_id=12345,
            season_number=1,
            episode_number=5,
            watched_at=datetime(2025, 1, 15, 12, 0, 0),
            source="trakt",
        )
        a2 = WatchActivity(
            tmdb_show_id=12345,
            season_number=1,
            episode_number=5,
            watched_at=datetime(2025, 1, 16, 12, 0, 0),
            source="trakt",
        )
        
        assert a1.key != a2.key
        assert a1 != a2
