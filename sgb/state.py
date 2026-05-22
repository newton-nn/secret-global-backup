""".secret-global-backup hidden state directory management.

Mirrors git's .git directory pattern — stores all backup state
in a single hidden directory. The state directory itself IS the git repo root.
"""

import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path


class StateError(Exception):
    """State management error."""


class State:
    """Manages the .secret-global-backup hidden state directory.

    The state_dir itself serves as the git repo root. Git metadata
    lives in state_dir/.git/. Backup data lives in state_dir/staging/.
    """

    STAGING_DIR = "staging"
    MANIFEST_FILE = "manifest.json"
    ENCRYPT_MANIFEST_FILE = "encrypt_manifest.json"
    STATE_FILE = "state.json"
    KEYFILE = "keyfile.enc"

    def __init__(self, state_dir: Path):
        self.state_dir = state_dir
        self.staging_dir = state_dir / self.STAGING_DIR
        self.manifest_path = state_dir / self.MANIFEST_FILE
        self.encrypt_manifest_path = state_dir / self.ENCRYPT_MANIFEST_FILE
        self.state_path = state_dir / self.STATE_FILE
        self.keyfile_path = state_dir / self.KEYFILE

    @property
    def repo_root(self) -> Path:
        """The git repository root directory (state_dir itself)."""
        return self.state_dir

    def exists(self) -> bool:
        return self.state_dir.exists()

    def initialize(self) -> bool:
        """Initialize the state directory structure. Returns True if new, False if already exists."""
        if self.exists():
            return False
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.staging_dir.mkdir(parents=True, exist_ok=True)
        self._write_state({
            "created_at": datetime.now(timezone.utc).isoformat(),
            "version": 1,
            "last_backup": None,
            "total_backups": 0,
        })
        self._write_manifest({})
        # Write gitignore to keep metadata files out of version control
        gitignore = self.state_dir / ".gitignore"
        gitignore.write_text(
            "manifest.json\n"
            "encrypt_manifest.json\n"
            "state.json\n"
            "keyfile.enc\n"
            ".gitignore\n"
        )
        return True

    def _write_state(self, data: dict):
        self.state_path.write_text(json.dumps(data, indent=2))

    def _read_state(self) -> dict:
        if not self.state_path.exists():
            return {}
        return json.loads(self.state_path.read_text())

    def _write_manifest(self, data: dict):
        self.manifest_path.write_text(json.dumps(data, indent=2, sort_keys=True))

    def read_manifest(self) -> dict:
        if not self.manifest_path.exists():
            return {}
        return json.loads(self.manifest_path.read_text())

    def update_manifest_entry(self, path: str, info: dict):
        manifest = self.read_manifest()
        manifest[path] = info
        self._write_manifest(manifest)

    def get_state(self) -> dict:
        return self._read_state()

    def record_backup(self, commit_hash: str, source_count: int, file_count: int, db_count: int):
        """Record a successful backup."""
        state = self._read_state()
        state["last_backup"] = datetime.now(timezone.utc).isoformat()
        state["total_backups"] = state.get("total_backups", 0) + 1
        state["last_commit"] = commit_hash
        state["last_stats"] = {
            "sources": source_count,
            "files": file_count,
            "databases": db_count,
        }
        self._write_state(state)

    def increment_version(self):
        state = self._read_state()
        state["version"] = state.get("version", 0) + 1
        self._write_state(state)

    def clean_staging(self):
        """Remove all files from staging area."""
        if self.staging_dir.exists():
            shutil.rmtree(self.staging_dir)
            self.staging_dir.mkdir(parents=True, exist_ok=True)

    def staging_path_for(self, source_name: str, rel_path: str) -> Path:
        """Get the staging path for a file from a source."""
        return self.staging_dir / source_name / rel_path

    def ensure_staging_dir(self, source_name: str, rel_dir: str = ""):
        """Ensure staging directory exists."""
        d = self.staging_dir / source_name / rel_dir
        d.mkdir(parents=True, exist_ok=True)
        return d

    def get_db_staging_dir(self) -> Path:
        d = self.staging_dir / "_databases"
        d.mkdir(parents=True, exist_ok=True)
        return d
