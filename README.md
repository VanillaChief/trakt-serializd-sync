# trakt-serializd-sync

[![Built with AI assistance](https://img.shields.io/badge/Built%20with-AI%20assistance-blueviolet)](.github/AI-ATTRIBUTION.md)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Two-way continuous sync between [Trakt](https://trakt.tv) and [Serializd](https://serializd.com) watch history, ratings, and diary entries.

## Features

- **Bidirectional sync** - Watch history flows both ways
- **Diary entries** - Preserves watch dates and timestamps
- **Ratings sync** - Syncs episode/show ratings (Serializd 0-10 → Trakt 1-10)
- **Rewatch support** - Multiple views of the same episode are tracked
- **Conflict resolution** - Configurable strategies (trakt-wins, serializd-wins, newest-wins)
- **Continuous mode** - Run as a daemon with configurable polling interval
- **Incremental sync** - Only syncs changes since last run

## Installation

```bash
git clone https://github.com/VanillaChief/trakt-serializd-sync.git
cd trakt-serializd-sync
python -m venv venv
source venv/bin/activate
pip install -e .
```

## Configuration

### First-time setup

```bash
# Authenticate with Trakt (opens browser for OAuth)
trakt-serializd-sync auth trakt

# Authenticate with Serializd
trakt-serializd-sync auth serializd
```

### Environment variables (optional)

```bash
export SERIALIZD_EMAIL="your@email.com"
export SERIALIZD_PASSWORD="your-password"
```

## Usage

### One-time sync

```bash
# Sync in both directions
trakt-serializd-sync sync

# Sync only from Trakt to Serializd
trakt-serializd-sync sync --direction trakt-to-serializd

# Sync only from Serializd to Trakt
trakt-serializd-sync sync --direction serializd-to-trakt

# Dry run (show what would be synced)
trakt-serializd-sync sync --dry-run
```

### Continuous sync (daemon mode)

```bash
# Run continuously with 15-minute interval
trakt-serializd-sync sync --watch

# Custom interval (in minutes)
trakt-serializd-sync sync --watch --interval 30
```

### Conflict resolution

```bash
# Trakt always wins conflicts (default)
trakt-serializd-sync sync --conflict-strategy trakt-wins

# Serializd always wins conflicts
trakt-serializd-sync sync --conflict-strategy serializd-wins

# Most recent timestamp wins
trakt-serializd-sync sync --conflict-strategy newest-wins
```

### Other commands

```bash
# Show sync status and statistics
trakt-serializd-sync status

# Reset sync state (will re-sync everything)
trakt-serializd-sync reset-state
```

## Systemd Service

For running as a system service:

```bash
# Copy service file
sudo cp systemd/trakt-serializd-sync.service /etc/systemd/system/

# Edit paths and user as needed
sudo systemctl edit trakt-serializd-sync

# Enable and start
sudo systemctl enable --now trakt-serializd-sync

# Check logs
journalctl -u trakt-serializd-sync -f
```

## Data Storage

| File | Purpose |
|------|---------|
| `~/.local/share/trakt-serializd-sync/trakt_token.json` | Trakt OAuth tokens |
| `~/.local/share/trakt-serializd-sync/serializd_token.json` | Serializd credentials |
| `~/.local/share/trakt-serializd-sync/sync_state.json` | Last sync timestamps and ledger |

## Limitations

- Serializd API is unofficial/reverse-engineered and may break
- Reviews/tags are not synced (Trakt has no equivalent)
- Watchlist sync is not yet implemented
- Show-level ratings only sync if episode-level data exists

## Related Projects

- [trakt-to-serializd](https://github.com/VanillaChief/trakt-to-serializd) - One-way migration tool
- [serializd-py](https://github.com/VanillaChief/serializd-py) - Serializd API client library

## License

MIT - see [LICENSE](LICENSE)
