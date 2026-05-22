"""Configuration loader and validator."""

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


DEFAULT_CONFIG_FILENAME = "sgb.yaml"
DEFAULT_STATE_DIR = ".secret-global-backup"


class ConfigError(Exception):
    """Configuration validation error."""


class Config:
    """Backup configuration loaded from YAML."""

    def __init__(self, path: Optional[Path] = None):
        self.path = path or Path.cwd() / DEFAULT_CONFIG_FILENAME
        self.data: Dict[str, Any] = {}
        self._loaded = False

    def load(self) -> Dict[str, Any]:
        """Load and validate configuration."""
        if not self.path.exists():
            raise ConfigError(f"Config file not found: {self.path}\nRun 'sgb init' to create one.")

        with open(self.path) as f:
            self.data = yaml.safe_load(f) or {}

        self._resolve_env_vars(self.data)
        self._validate()
        self._loaded = True
        return self.data

    @property
    def sources(self) -> List[Dict[str, Any]]:
        return self.data.get("sources", [])

    @property
    def encryption_key(self) -> Optional[str]:
        return self.data.get("encryption_key")

    @property
    def remote_url(self) -> Optional[str]:
        remote = self.data.get("remote", {})
        return remote.get("url")

    @property
    def remote_branch(self) -> str:
        remote = self.data.get("remote", {})
        return remote.get("branch", "main")

    @property
    def schedule_interval_minutes(self) -> int:
        schedule = self.data.get("schedule", {})
        return schedule.get("interval_minutes", 60)

    @property
    def state_dir(self) -> Path:
        custom = self.data.get("state_dir")
        if custom:
            return Path(os.path.expandvars(os.path.expanduser(custom)))
        return Path.cwd() / DEFAULT_STATE_DIR

    def get_source_paths(self) -> List[Dict[str, Any]]:
        """Return resolved source entries with absolute paths."""
        resolved = []
        for source in self.sources:
            entry = dict(source)
            if entry.get("type") == "directory":
                p = entry.get("path", "")
                entry["path"] = str(Path(os.path.expandvars(os.path.expanduser(p))).resolve())
            elif entry.get("type") in ("sqlite",):
                p = entry.get("path", "")
                if p:
                    entry["path"] = str(Path(os.path.expandvars(os.path.expanduser(p))).resolve())
            resolved.append(entry)
        return resolved

    def get_ignore_patterns(self, source_name: str) -> List[str]:
        """Get ignore patterns for a source, combining config + .sgbignore file."""
        patterns = []
        for source in self.sources:
            if source.get("name") == source_name:
                patterns.extend(source.get("ignore", []))
                if source.get("type") == "directory":
                    src_path = Path(os.path.expandvars(os.path.expanduser(source.get("path", ""))))
                    ignore_file = src_path / ".sgbignore"
                    if ignore_file.exists():
                        with open(ignore_file) as f:
                            patterns.extend(line.strip() for line in f if line.strip() and not line.startswith("#"))
                break
        return patterns

    def get_encrypt_patterns(self, source_name: str) -> List[str]:
        """Get encryption patterns for a source."""
        for source in self.sources:
            if source.get("name") == source_name:
                encrypt = source.get("encrypt", [])
                if isinstance(encrypt, bool):
                    return ["**/*"] if encrypt else []
                if isinstance(encrypt, list):
                    return encrypt
                return []
        return []

    def is_file_encrypted(self, source_name: str, rel_path: str) -> bool:
        """Check if a file matches encryption patterns."""
        import fnmatch
        patterns = self.get_encrypt_patterns(source_name)
        for pattern in patterns:
            if fnmatch.fnmatch(rel_path, pattern):
                return True
        return False

    @staticmethod
    def _resolve_env_vars(obj: Any):
        """Recursively resolve ${VAR} and $VAR references in config values."""
        if isinstance(obj, dict):
            for k, v in obj.items():
                if isinstance(v, str):
                    obj[k] = os.path.expandvars(v)
                elif isinstance(v, (dict, list)):
                    Config._resolve_env_vars(v)
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                if isinstance(v, str):
                    obj[i] = os.path.expandvars(v)
                elif isinstance(v, (dict, list)):
                    Config._resolve_env_vars(v)

    def _validate(self):
        """Validate configuration structure."""
        if "sources" not in self.data or not self.data["sources"]:
            raise ConfigError("No backup sources defined in config.")

        valid_types = {"directory", "sqlite", "postgres", "mysql"}
        for i, source in enumerate(self.data["sources"]):
            name = source.get("name", f"source-{i}")
            if "type" not in source:
                raise ConfigError(f"Source '{name}' missing 'type' field.")
            if source["type"] not in valid_types:
                raise ConfigError(f"Source '{name}': invalid type '{source['type']}'. Valid: {valid_types}")
            if source["type"] == "directory" and "path" not in source:
                raise ConfigError(f"Directory source '{name}' missing 'path'.")
            if source["type"] == "sqlite" and "path" not in source:
                raise ConfigError(f"SQLite source '{name}' missing 'path'.")

    def generate_example(self) -> str:
        """Generate an example config file."""
        return """# Secret Global Backup Configuration
version: "1.0"

# Encryption key — use env var for safety: ${SGB_KEY}
encryption_key: "change-me-to-a-strong-passphrase"

# Optional: push backups to a git remote
# remote:
#   url: "git@github.com:you/backup-repo.git"
#   branch: "main"

# Optional: automatic backup schedule
# schedule:
#   interval_minutes: 60

sources:
  # Directory backup with ignore and encrypt patterns
  - name: "project-files"
    type: directory
    path: "./important-files"
    ignore:
      - "node_modules/"
      - "*.log"
      - "__pycache__/"
      - ".git/"
    encrypt:
      - "**/secrets/**"
      - "**/.env"
      - "**/credentials.*"

  # SQLite database backup
  - name: "app-db"
    type: sqlite
    path: "./data/app.db"
    encrypt: true

  # PostgreSQL database backup
  # - name: "pg-db"
  #   type: postgres
  #   host: "localhost"
  #   port: 5432
  #   database: "myapp"
  #   user: "backup_user"
  #   password: "${DB_PASS}"
  #   encrypt: true

  # MySQL database backup
  # - name: "mysql-db"
  #   type: mysql
  #   host: "localhost"
  #   port: 3306
  #   database: "myapp"
  #   user: "backup_user"
  #   password: "${DB_PASS}"
  #   encrypt: true
"""
