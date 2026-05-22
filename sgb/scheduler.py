"""Interval-based backup scheduling.

Uses the `schedule` library for periodic execution.
Can run as a foreground daemon or one-shot.
"""

import signal
import sys
import time
from pathlib import Path
from typing import Optional

import schedule as schedule_lib

from .config import Config
from .engine import BackupEngine


class SchedulerError(Exception):
    """Scheduler error."""


class BackupScheduler:
    """Manages periodic backup execution."""

    def __init__(self, config: Config):
        self.config = config
        self.engine = BackupEngine(config)
        self._running = False
        self._last_error: Optional[str] = None

    def run_once(self, push: bool = True) -> dict:
        """Run a single backup cycle."""
        stats = self.engine.backup(dry_run=False)
        if push and self.config.remote_url:
            self.engine.push_to_remote()
        return stats

    def start_daemon(self, push: bool = True):
        """Start the backup daemon with configured interval."""
        interval = self.config.schedule_interval_minutes

        def job():
            try:
                stats = self.engine.backup(dry_run=False)
                print(f"[{stats['timestamp']}] Backup complete: "
                      f"{stats['files']} files, {stats['databases']} databases, "
                      f"commit: {stats['commit'][:8]}")
                if push and self.config.remote_url:
                    self.engine.push_to_remote()
                    print(f"  Pushed to remote: {self.config.remote_url}")
            except Exception as e:
                self._last_error = str(e)
                print(f"[ERROR] Backup failed: {e}", file=sys.stderr)

        # Run immediately on start
        job()

        # Schedule periodic runs
        schedule_lib.every(interval).minutes.do(job)

        # Handle signals
        def handle_signal(signum, frame):
            print("\nShutting down backup daemon...")
            self._running = False
        signal.signal(signal.SIGINT, handle_signal)
        signal.signal(signal.SIGTERM, handle_signal)

        self._running = True
        print(f"Backup daemon running. Interval: {interval} minutes. Press Ctrl+C to stop.")
        while self._running:
            schedule_lib.run_pending()
            time.sleep(1)
