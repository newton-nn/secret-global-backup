"""CLI entry point for Secret Global Backup."""

import json
import os
import sys
from pathlib import Path
from typing import Optional

import click

from .config import Config, ConfigError
from .engine import BackupEngine, EngineError
from .encryptor import Encryptor, EncryptorError, EncryptManifest
from .restore import Restorer, RestoreError
from .scheduler import BackupScheduler
from .state import State


def _load_config(config_path: Optional[str] = None) -> Config:
    """Load and validate config."""
    path = Path(config_path) if config_path else None
    cfg = Config(path)
    try:
        cfg.load()
    except ConfigError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    return cfg


@click.group()
@click.version_option(version="1.0.0")
def main():
    """Secret Global Backup — configurable encrypted backup system."""
    pass


@main.command()
@click.option("--key", "-k", help="Encryption passphrase", prompt=True, hide_input=True)
@click.option("--key-confirm", help="Confirm passphrase", prompt=True, hide_input=True)
@click.option("--path", "-p", default=".", help="Path to initialize in")
def init(key: str, key_confirm: str, path: str):
    """Initialize a new backup configuration."""
    if key != key_confirm:
        click.echo("Error: Passphrases do not match.", err=True)
        sys.exit(1)

    if len(key) < 8:
        click.echo("Error: Passphrase must be at least 8 characters.", err=True)
        sys.exit(1)

    target = Path(path).resolve()

    # Create state directory
    state = State(target / Config.DEFAULT_STATE_DIR)
    is_new = state.initialize()

    if not is_new:
        click.echo("Backup state already exists here. Use --path to specify a different location.")
        sys.exit(1)

    # Generate example config
    cfg = Config(target / Config.DEFAULT_CONFIG_FILENAME)
    example = cfg.generate_example()
    # Replace placeholder with actual key
    example = example.replace('encryption_key: "change-me-to-a-strong-passphrase"',
                              f'encryption_key: "{key}"')
    cfg.path.write_text(example)

    click.echo(f"✅ Initialized backup at: {target}")
    click.echo(f"   Config: {cfg.path}")
    click.echo(f"   State:  {state.state_dir}")
    click.echo(f"   Edit {cfg.path} to configure your backup sources.")
    click.echo("")
    click.echo("⚠️  Store your encryption key safely! Without it, you CANNOT restore backups.")


@main.command()
@click.option("--config", "-c", "config_path", help="Config file path")
@click.option("--daemon", "-d", is_flag=True, help="Run as background daemon")
@click.option("--no-push", is_flag=True, help="Skip remote push")
@click.option("--dry-run", is_flag=True, help="Preview without committing")
def backup(config_path: str, daemon: bool, no_push: bool, dry_run: bool):
    """Run a backup."""
    cfg = _load_config(config_path)

    if daemon:
        scheduler = BackupScheduler(cfg)
        try:
            scheduler.start_daemon(push=not no_push)
        except KeyboardInterrupt:
            click.echo("\nBackup daemon stopped.")
    else:
        try:
            engine = BackupEngine(cfg)
            stats = engine.backup(dry_run=dry_run)

            if dry_run:
                click.echo(f"Dry run: would backup {stats['files']} files, "
                           f"{stats['databases']} databases from {stats['sources']} sources.")
                return

            click.echo(f"✅ Backup complete: {stats['files']} files, "
                       f"{stats['databases']} databases, "
                       f"{stats['encrypted']} encrypted")
            if stats["commit"]:
                click.echo(f"   Commit: {stats['commit'][:12]}")

            if not no_push and cfg.remote_url:
                engine.push_to_remote()
                click.echo(f"   Pushed to: {cfg.remote_url}")

        except EngineError as e:
            click.echo(f"Error: {e}", err=True)
            sys.exit(1)


@main.command()
@click.option("--config", "-c", "config_path", help="Config file path")
@click.option("--version", "-v", "version_hash", help="Restore specific version")
@click.option("--target", "-t", help="Override restore target directory")
@click.option("--source", "-s", "source_name", multiple=True, help="Restore specific source only")
@click.option("--dry-run", is_flag=True, help="Preview restore without executing")
def restore(config_path: str, version_hash: str, target: str,
            source_name: tuple, dry_run: bool):
    """Restore files from backup."""
    cfg = _load_config(config_path)

    try:
        encryptor = Encryptor(cfg.encryption_key)
        state = State(cfg.state_dir)
        restorer = Restorer(cfg, encryptor, state)

        if dry_run:
            click.echo("Dry run: would restore files to their original locations.")
            return

        sources = list(source_name) if source_name else None
        target_path = Path(target) if target else None

        stats = restorer.restore_all(specific_sources=sources, target_override=target_path)
        click.echo(f"✅ Restored {stats['files']} files from {stats['sources']} sources.")

    except (EncryptorError, RestoreError) as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@main.command()
@click.option("--config", "-c", "config_path", help="Config file path")
def versions(config_path: str):
    """List available backup versions."""
    cfg = _load_config(config_path)
    try:
        engine = BackupEngine(cfg)
        vers = engine.get_versions()
        if not vers:
            click.echo("No backups found.")
            return
        for v in vers:
            click.echo(f"{v['hash'][:12]}  {v['date']}  {v['message']}")
    except EngineError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@main.command()
@click.option("--config", "-c", "config_path", help="Config file path")
def status(config_path: str):
    """Show current backup status."""
    cfg = _load_config(config_path)
    try:
        engine = BackupEngine(cfg)
        st = engine.get_status()
        click.echo(f"State directory:     {st['state_dir']}")
        click.echo(f"Initialized:         {st['initialized']}")
        click.echo(f"Last backup:         {st['last_backup'] or 'Never'}")
        click.echo(f"Total backups:       {st['total_backups']}")
        click.echo(f"Remote configured:   {st['remote_configured']}")
        click.echo(f"Sources configured:  {st['sources_configured']}")
        if st["last_stats"]:
            click.echo(f"Last backup stats:   {json.dumps(st['last_stats'])}")
    except EngineError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@main.command()
@click.option("--config", "-c", "config_path", help="Config file path")
@click.option("--new-key", "-k", help="New encryption passphrase", prompt=True, hide_input=True)
def rotate_key(config_path: str, new_key: str):
    """Rotate encryption key — decrypt with old key, re-encrypt with new."""
    cfg = _load_config(config_path)
    click.echo("Key rotation is available but requires a full re-encryption pass.")
    click.echo("This is a safety-critical operation. Please back up your data first.")
    click.echo("Feature coming in v1.1.")


@main.command()
@click.option("--config", "-c", "config_path", help="Config file path")
@click.option("--type", "-t", "db_type", help="Database type", type=click.Choice(["sqlite", "postgres", "mysql"]))
@click.option("--path", "-p", "db_path", help="Database path (SQLite) or host (PG/MySQL)")
@click.option("--output", "-o", help="Output file path")
def db_dump(config_path: str, db_type: str, db_path: str, output: str):
    """Dump a database without running a full backup."""
    if not db_type:
        click.echo("Error: --type is required", err=True)
        sys.exit(1)
    if not db_path:
        click.echo("Error: --path is required", err=True)
        sys.exit(1)

    from .db import dump_sqlite, dump_postgres, dump_mysql
    output_path = Path(output) if output else Path(f"dump_{db_type}.sql")

    try:
        if db_type == "sqlite":
            dump_sqlite(Path(db_path), output_path)
            click.echo(f"Dumped SQLite DB to: {output_path}")
        else:
            click.echo("Use full backup config for PostgreSQL/MySQL dumps.")
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@main.command()
def validate():
    """Validate the current configuration."""
    cfg = _load_config(None)
    click.echo("✅ Configuration is valid.")
    click.echo(f"   Sources: {len(cfg.sources)}")
    for s in cfg.sources:
        click.echo(f"   - {s['name']} ({s['type']})")
    if cfg.remote_url:
        click.echo(f"   Remote: {cfg.remote_url}")
    if cfg.schedule_interval_minutes:
        click.echo(f"   Schedule: every {cfg.schedule_interval_minutes} minutes")


if __name__ == "__main__":
    main()
