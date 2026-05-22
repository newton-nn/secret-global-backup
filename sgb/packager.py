"""Folder tree packaging with ignore and encryption support.

Walks directory trees, applies .sgbignore-style patterns,
encrypts matched files, and copies everything to the staging area.
"""

import fnmatch
import os
import shutil
from pathlib import Path
from typing import List, Optional, Set

from .config import Config
from .encryptor import Encryptor, EncryptManifest


class PackagerError(Exception):
    """Packaging error."""


class Packager:
    """Handles directory tree packaging for backup."""

    DEFAULT_IGNORE_PATTERNS = [
        ".sgbignore",
        ".secret-global-backup/",
        ".git/",
        "__pycache__/",
        "*.pyc",
        ".DS_Store",
        "Thumbs.db",
    ]

    def __init__(self, config: Config, encryptor: Encryptor, staging_dir: Path):
        self.config = config
        self.encryptor = encryptor
        self.staging_dir = staging_dir
        self._file_count = 0
        self._encrypted_count = 0

    @property
    def file_count(self) -> int:
        return self._file_count

    @property
    def encrypted_count(self) -> int:
        return self._encrypted_count

    def should_ignore(self, rel_path: str, ignore_patterns: List[str]) -> bool:
        """Check if a relative path matches any ignore pattern."""
        parts = rel_path.replace("\\", "/").split("/")
        all_patterns = list(self.DEFAULT_IGNORE_PATTERNS) + list(ignore_patterns)
        for pattern in all_patterns:
            # Match against full relative path
            if fnmatch.fnmatch(rel_path, pattern):
                return True
            # Match against each path component (for directory patterns)
            for part in parts:
                if fnmatch.fnmatch(part, pattern):
                    return True
            # Match path with trailing / for directory patterns
            if pattern.endswith("/") and rel_path.startswith(pattern.rstrip("/")):
                return True
        return False

    def should_encrypt(self, rel_path: str, encrypt_patterns: List[str]) -> bool:
        """Check if a relative path matches any encryption pattern."""
        if not encrypt_patterns:
            return False
        for pattern in encrypt_patterns:
            if fnmatch.fnmatch(rel_path, pattern):
                return True
            # Handle ** patterns by converting to regex-like matching
            if "**" in pattern:
                # Convert glob pattern to check if path matches via components
                # "**/secrets/**" matches "secrets/x" or "a/secrets/x"
                # "**/.env" matches ".env" or "a/.env"
                if pattern.startswith("**/"):
                    rest = pattern[3:]  # Remove "**/"
                    # Check if path ends with rest or has rest as a component
                    if rel_path == rest:
                        return True
                    if "/" + rest in rel_path:
                        return True
                    if fnmatch.fnmatch(rel_path, "*/" + rest):
                        return True
                    if fnmatch.fnmatch(rel_path, rest):
                        return True
        return False

    def package_directory(self, source: dict, encrypt_manifest: EncryptManifest) -> int:
        """Package a directory source. Returns number of files processed."""
        source_path = Path(source["path"])
        source_name = source.get("name", source_path.name)

        if not source_path.exists():
            raise PackagerError(f"Source directory not found: {source_path}")

        ignore_patterns = self.config.get_ignore_patterns(source_name)
        encrypt_patterns = self.config.get_encrypt_patterns(source_name)
        source_base = str(source_path)

        count = 0
        for root, dirs, files in os.walk(source_path):
            # Filter directories in-place to skip ignored ones
            dirs[:] = [
                d for d in dirs
                if not self.should_ignore(
                    os.path.relpath(os.path.join(root, d), source_base) + "/",
                    ignore_patterns
                )
            ]

            for filename in files:
                abs_path = os.path.join(root, filename)
                rel_path = os.path.relpath(abs_path, source_base)

                if self.should_ignore(rel_path, ignore_patterns):
                    continue

                staging_path = self.staging_dir / source_name / rel_path
                staging_path.parent.mkdir(parents=True, exist_ok=True)

                if self.should_encrypt(rel_path, encrypt_patterns):
                    # Encrypt the file
                    encrypted = self.encryptor.encrypt_stream(Path(abs_path))
                    enc_staging_path = Path(str(staging_path) + ".enc")
                    enc_staging_path.write_bytes(encrypted)
                    encrypt_manifest.add(
                        original_path=f"{source_name}/{rel_path}",
                        encrypted_path=f"{source_name}/{rel_path}.enc",
                        salt_hex=self.encryptor.salt_hex,
                        iv_hex="embedded",
                    )
                    self._encrypted_count += 1
                else:
                    # Copy as-is
                    shutil.copy2(abs_path, staging_path)

                count += 1
                self._file_count += 1

        return count

    def collect_all_sources(self, encrypt_manifest: EncryptManifest) -> dict:
        """Process all directory sources. Returns stats dict."""
        stats = {"directories": 0, "files": 0, "encrypted": 0}
        for source in self.config.sources:
            if source.get("type") != "directory":
                continue
            n = self.package_directory(source, encrypt_manifest)
            stats["directories"] += 1
            stats["files"] += n
            stats["encrypted"] += self._encrypted_count
        return stats
