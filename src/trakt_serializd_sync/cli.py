# AI-generated: Click CLI for trakt-serializd-sync
"""Command-line interface for trakt-serializd-sync."""

import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

import click
from platformdirs import user_data_dir

from trakt_serializd_sync import __version__
from trakt_serializd_sync.clients import SerializdClient, TraktClient
from trakt_serializd_sync.consts import DEFAULT_SYNC_INTERVAL_MINUTES
from trakt_serializd_sync.exceptions import SyncError, TraktAuthError, SerializdAuthError
from trakt_serializd_sync.models import ConflictStrategy, SyncDirection
from trakt_serializd_sync.state import SyncState
from trakt_serializd_sync.sync import SyncEngine


def setup_logging(verbose: bool = False) -> None:
    """Configure logging."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    )
    # Quiet httpx
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def get_data_dir() -> Path:
    """Get the data directory."""
    return Path(user_data_dir("trakt-serializd-sync"))


@click.group()
@click.version_option(version=__version__)
@click.option('-v', '--verbose', is_flag=True, help='Enable debug logging')
@click.pass_context
def cli(ctx: click.Context, verbose: bool) -> None:
    """Two-way sync between Trakt and Serializd."""
    setup_logging(verbose)
    ctx.ensure_object(dict)
    ctx.obj['verbose'] = verbose
    ctx.obj['data_dir'] = get_data_dir()


@cli.group()
def auth() -> None:
    """Authenticate with Trakt or Serializd."""
    pass


@auth.command('trakt')
@click.pass_context
def auth_trakt(ctx: click.Context) -> None:
    """Authenticate with Trakt using OAuth device flow."""
    data_dir = ctx.obj['data_dir']
    client = TraktClient(data_dir=data_dir)
    
    click.echo("🔑 Starting Trakt authentication...")
    
    try:
        token_data = client.login()
        user_info = client.get_user_info()
        username = user_info.get('user', {}).get('username', 'Unknown')
        
        click.echo(f"✅ Authenticated as: {username}")
        click.echo(f"📁 Token saved to: {client.token_file}")
    except TraktAuthError as e:
        click.echo(f"❌ Authentication failed: {e}", err=True)
        sys.exit(1)


@auth.command('serializd')
@click.option('--email', prompt=True, help='Serializd email')
@click.option('--password', prompt=True, hide_input=True, help='Serializd password')
@click.pass_context
def auth_serializd(ctx: click.Context, email: str, password: str) -> None:
    """Authenticate with Serializd using email/password."""
    data_dir = ctx.obj['data_dir']
    client = SerializdClient(data_dir=data_dir)
    
    click.echo("🔑 Logging in to Serializd...")
    
    try:
        client.login(email=email, password=password)
        click.echo(f"✅ Authenticated as: {client.username}")
        click.echo(f"📁 Token saved to: {client.token_file}")
    except SerializdAuthError as e:
        click.echo(f"❌ Authentication failed: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option(
    '--direction', '-d',
    type=click.Choice(['both', 'trakt-to-serializd', 'serializd-to-trakt']),
    default='both',
    help='Sync direction',
)
@click.option(
    '--conflict-strategy', '-c',
    type=click.Choice(['trakt-wins', 'serializd-wins', 'newest-wins']),
    default='trakt-wins',
    help='How to resolve conflicts',
)
@click.option('--dry-run', is_flag=True, help='Show what would be synced without making changes')
@click.option('--watch', '-w', is_flag=True, help='Run continuously')
@click.option('--interval', '-i', default=DEFAULT_SYNC_INTERVAL_MINUTES, help='Sync interval in minutes (with --watch)')
@click.pass_context
def sync(
    ctx: click.Context,
    direction: str,
    conflict_strategy: str,
    dry_run: bool,
    watch: bool,
    interval: int,
) -> None:
    """Sync watch history between Trakt and Serializd."""
    data_dir = ctx.obj['data_dir']
    
    # Initialize clients
    trakt = TraktClient(data_dir=data_dir)
    serializd = SerializdClient(data_dir=data_dir)
    state = SyncState(data_dir=data_dir)
    
    # Load tokens
    if not trakt.load_saved_token():
        click.echo("❌ Not authenticated with Trakt. Run: trakt-serializd-sync auth trakt", err=True)
        sys.exit(1)
    
    if not serializd.load_saved_token():
        click.echo("❌ Not authenticated with Serializd. Run: trakt-serializd-sync auth serializd", err=True)
        sys.exit(1)
    
    # Parse options
    sync_direction = SyncDirection(direction)
    strategy = ConflictStrategy(conflict_strategy)
    
    def progress_callback(msg: str) -> None:
        click.echo(f"  {msg}")
    
    engine = SyncEngine(
        trakt=trakt,
        serializd=serializd,
        state=state,
        conflict_strategy=strategy,
        dry_run=dry_run,
        progress_callback=progress_callback,
    )
    
    def run_sync() -> None:
        click.echo(f"\n🔄 Starting sync ({direction})...")
        if dry_run:
            click.echo("  [DRY RUN MODE]")
        
        try:
            results = engine.sync(direction=sync_direction)
            
            click.echo("\n📊 Results:")
            click.echo(f"  Trakt → Serializd: {results['trakt_to_serializd']}")
            click.echo(f"  Serializd → Trakt: {results['serializd_to_trakt']}")
            if results['conflicts']:
                click.echo(f"  Conflicts resolved: {results['conflicts']}")
            if results['errors']:
                click.echo(f"  Errors: {results['errors']}")
            
        except SyncError as e:
            click.echo(f"\n❌ Sync failed: {e}", err=True)
    
    if watch:
        click.echo(f"👀 Watch mode enabled. Syncing every {interval} minutes.")
        click.echo("   Press Ctrl+C to stop.\n")
        
        while True:
            run_sync()
            click.echo(f"\n⏰ Next sync at: {datetime.now().strftime('%H:%M')} + {interval}min")
            try:
                time.sleep(interval * 60)
            except KeyboardInterrupt:
                click.echo("\n👋 Stopping...")
                break
    else:
        run_sync()


@cli.command()
@click.pass_context
def status(ctx: click.Context) -> None:
    """Show sync status and statistics."""
    data_dir = ctx.obj['data_dir']
    state = SyncState(data_dir=data_dir)
    
    status_info = state.get_status()
    
    click.echo("📊 Sync Status\n")
    
    if status_info['last_sync']:
        click.echo(f"Last sync: {status_info['last_sync']}")
    else:
        click.echo("Last sync: Never")
    
    click.echo(f"\n🎬 Trakt:")
    trakt_info = status_info['trakt']
    click.echo(f"  Last fetched: {trakt_info['last_fetched'] or 'Never'}")
    click.echo(f"  Last watched: {trakt_info['last_watched'] or 'Unknown'}")
    
    click.echo(f"\n📺 Serializd:")
    serializd_info = status_info['serializd']
    click.echo(f"  Last fetched: {serializd_info['last_fetched'] or 'Never'}")
    click.echo(f"  Last diary: {serializd_info['last_diary'] or 'Unknown'}")
    
    click.echo(f"\n📈 Statistics:")
    stats = status_info['stats']
    click.echo(f"  Total syncs: {stats.get('total_syncs', 0)}")
    click.echo(f"  Trakt → Serializd: {stats.get('trakt_to_serializd', 0)}")
    click.echo(f"  Serializd → Trakt: {stats.get('serializd_to_trakt', 0)}")
    click.echo(f"  Conflicts resolved: {stats.get('conflicts_resolved', 0)}")
    click.echo(f"  Errors: {stats.get('errors', 0)}")
    
    click.echo(f"\n📁 Synced activities: {status_info['synced_activities']}")
    click.echo(f"📂 Data directory: {data_dir}")


@cli.command('reset-state')
@click.option('--yes', '-y', is_flag=True, help='Skip confirmation')
@click.pass_context
def reset_state(ctx: click.Context, yes: bool) -> None:
    """Reset sync state (will re-sync everything on next run)."""
    if not yes:
        click.confirm('This will reset all sync state. Continue?', abort=True)
    
    data_dir = ctx.obj['data_dir']
    state = SyncState(data_dir=data_dir)
    state.reset()
    
    click.echo("✅ Sync state reset")


if __name__ == '__main__':
    cli()
