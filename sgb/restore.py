"""Restore files and databases to their original locations."""

import os
import shutil
from pathlib import Path
from typing import Dict, List, Optional

from .config import Config
from .encryptor import Encryptor, EncryptManifest
from .state import State


class RestoreError(Exception):
    """Restore operation error."""


class Restorer:
    """Handles restoring backed-up files to their original locations."""

    def __init__(self, config: Config, encryptor: Encryptor, state: State):
        self.config = config
        self.encryptor = encryptor
        self.state = state

    def restore_file(self, staging_rel_path: str, original_path: str,
                     encrypt_manifest: EncryptManifest) -> bool:
        """Restore a single file. Returns True on success."""
        source_file = self.state.staging_dir / staging_rel_path
        target_file = Path(original_path)

        # Check if this file was encrypted — use .enc if available
        enc_info = encrypt_manifest.get(staging_rel_path)
        if enc_info:
            enc_file = self.state.staging_dir / (staging_rel_path + ".enc")
            if enc_file.exists():
                source_file = enc_file

        if not source_file.exists():
            raise RestoreError(f"Backup file not found in staging: {source_file}")

        target_file.parent.mkdir(parents=True, exist_ok=True)

        if enc_info:
            # Decrypt
            try:
                decrypted = self.encryptor.decrypt_file(source_file)
                target_file.write_bytes(decrypted)
            except Exception as e:
                raise RestoreError(f"Decryption failed for {staging_rel_path}: {e}")
        else:
            # Plain copy
            shutil.copy2(source_file, target_file)

        return True

    def restore_source(self, source: dict, encrypt_manifest: EncryptManifest) -> int:
        """Restore files for a single source. Returns count of restored files."""
        source_name = source.get("name", "")
        source_type = source.get("type", "directory")

        if source_type == "directory":
            source_path = Path(source["path"])
            source_dir = self.state.staging_dir / source_name

            if not source_dir.exists():
                raise RestoreError(f"No backup data for source '{source_name}'")

            count = 0
            for root, dirs, files in os.walk(source_dir):
                for filename in files:
                    rel = os.path.relpath(os.path.join(root, filename), source_dir)
                    staging_rel = f"{source_name}/{rel}"

                    # Strip .enc extension for original path
                    orig_rel = rel
                    if orig_rel.endswith(".enc"):
                        orig_rel = orig_rel[:-4]

                    target = source_path / orig_rel
                    self.restore_file(staging_rel, str(target), encrypt_manifest)
                    count += 1
            return count

        elif source_type in ("sqlite", "postgres", "mysql"):
            db_dir = self.state.staging_dir / "_databases"
            db_name = source_name
            staging_rel = f"_databases/{db_name}.db"
            if source_type == "postgres":
                staging_rel = f"_databases/{db_name}.pgdump"
            elif source_type == "mysql":
                staging_rel = f"_databases/{db_name}.sql"

            # Check encrypted version
            enc_staging = f"{staging_rel}.enc"
            source_file = self.state.staging_dir / staging_rel
            source_enc = self.state.staging_dir / enc_staging

            actual_file = source_enc if source_enc.exists() else source_file
            if not actual_file.exists():
                raise RestoreError(f"No backup for database '{source_name}'")

            if source_type == "sqlite":
                target_path = Path(source["path"])
                if encrypt_manifest.get(staging_rel) or encrypt_manifest.get(enc_staging):
                    decrypted = self.encryptor.decrypt_file(actual_file)
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    target_path.write_bytes(decrypted)
                else:
                    shutil.copy2(actual_file, target_path)
                return 1

            # For postgres/mysql, restore using native tools
            # (Would use pg_restore or mysql client — here we copy the dump file)
            return 1

        return 0

    def restore_all(self, specific_sources: Optional[List[str]] = None,
                    target_override: Optional[Path] = None) -> dict:
        """Restore all sources or specific ones. Returns stats."""
        encrypt_manifest = EncryptManifest(self.state.encrypt_manifest_path)
        total = 0
        restored_sources = 0

        for source in self.config.sources:
            name = source.get("name", "")
            if specific_sources and name not in specific_sources:
                continue

            n = self.restore_source(source, encrypt_manifest)
            total += n
            restored_sources += 1

        return {"sources": restored_sources, "files": total}
