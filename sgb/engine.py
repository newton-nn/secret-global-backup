"""Core backup engine — orchestrates packaging, DB dumps, git versioning, and remote push."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .config import Config
from .encryptor import Encryptor, EncryptManifest
from .packager import Packager
from .db import DBHandler
from .remote import Remote
from .state import State


class EngineError(Exception):
    """Backup engine error."""


class BackupEngine:
    """Orchestrates the complete backup pipeline."""

    def __init__(self, config: Config):
        self.config = config

        key = config.encryption_key
        if not key:
            raise EngineError("No encryption key configured. Set 'encryption_key' in config.")

        self.encryptor = Encryptor(key)
        self.state = State(config.state_dir)
        self.remote = Remote(self.state.repo_root)

    def backup(self, dry_run: bool = False) -> dict:
        """Run a full backup. Returns stats dict."""
        timestamp = datetime.now(timezone.utc).isoformat()
        stats = {"sources": 0, "files": 0, "databases": 0, "encrypted": 0,
                 "commit": "", "timestamp": timestamp}

        # Ensure state and git repo exist
        self.state.initialize()
        self.remote.init_repo()

        # Clean staging
        self.state.clean_staging()

        # Load or create encrypt manifest
        encrypt_manifest = EncryptManifest(self.state.encrypt_manifest_path)

        # 1. Process directory sources
        packager = Packager(self.config, self.encryptor, self.state.staging_dir)
        dir_stats = packager.collect_all_sources(encrypt_manifest)
        stats["sources"] += dir_stats["directories"]
        stats["files"] += dir_stats["files"]
        stats["encrypted"] += dir_stats["encrypted"]

        # 2. Process database sources
        db_handler = DBHandler(self.encryptor, self.state.staging_dir)
        db_sources = [s for s in self.config.sources if s.get("type") not in ("directory",)]
        for source in db_sources:
            try:
                result = db_handler.dump_source(source, encrypt_manifest)
                if result:
                    stats["databases"] += 1
                    if result.endswith(".enc"):
                        stats["encrypted"] += 1
            except Exception as e:
                raise EngineError(f"Database backup failed for '{source.get('name')}': {e}")

        # 3. Build manifest
        manifest = {}
        db_sources_names = {s.get("name") for s in db_sources}
        for source in self.config.sources:
            name = source.get("name", "")
            if source.get("type") == "directory":
                src_dir = self.state.staging_dir / name
                if src_dir.exists():
                    for f in src_dir.rglob("*"):
                        if f.is_file():
                            rel = str(f.relative_to(self.state.staging_dir))
                            manifest[rel] = {"source": name, "backup_time": timestamp}

        for source in self.config.sources:
            if source.get("type") not in ("directory",):
                name = source.get("name", "")
                db_dir = self.state.staging_dir / "_databases"
                if db_dir.exists():
                    for f in db_dir.iterdir():
                        if f.is_file():
                            rel = str(f.relative_to(self.state.staging_dir))
                            manifest[rel] = {"source": name, "type": "database", "backup_time": timestamp}

        self.state._write_manifest(manifest)

        if dry_run:
            return stats

        # 4. Git commit
        commit_msg = f"Backup: {timestamp} — {stats['files']} files, {stats['databases']} databases"
        try:
            commit_hash = self.remote.commit(commit_msg)
            stats["commit"] = commit_hash
        except Exception as e:
            raise EngineError(f"Git commit failed: {e}")

        # 5. Record state
        self.state.record_backup(
            commit_hash=commit_hash,
            source_count=stats["sources"],
            file_count=stats["files"],
            db_count=stats["databases"],
        )

        return stats

    def push_to_remote(self) -> bool:
        """Push backup repository to configured remote."""
        remote_url = self.config.remote_url
        if not remote_url:
            raise EngineError("No remote URL configured.")

        branch = self.config.remote_branch
        self.remote.add_remote(remote_url)
        return self.remote.push(branch=branch)

    def get_versions(self) -> list:
        """Get list of backup versions."""
        return self.remote.get_log(max_count=50)

    def get_status(self) -> dict:
        """Get current backup status."""
        state_data = self.state.get_state()
        return {
            "state_dir": str(self.state.state_dir),
            "initialized": self.state.exists(),
            "last_backup": state_data.get("last_backup"),
            "total_backups": state_data.get("total_backups", 0),
            "last_commit": state_data.get("last_commit", ""),
            "last_stats": state_data.get("last_stats", {}),
            "remote_configured": bool(self.config.remote_url),
            "sources_configured": len(self.config.sources),
        }
