"""Tests for the restore module."""

import tempfile
from pathlib import Path

from sgb.config import Config
from sgb.encryptor import Encryptor, EncryptManifest
from sgb.restore import Restorer
from sgb.state import State


class TestRestorer:
    def test_restore_plain_file(self):
        """Test restoring a plain (non-encrypted) file."""
        # Setup
        src_dir = Path(tempfile.mkdtemp()) / "original"
        src_dir.mkdir(parents=True)
        (src_dir / "file.txt").write_text("original content")

        state_dir = Path(tempfile.mkdtemp()) / ".secret-global-backup"
        state = State(state_dir)
        state.initialize()

        # Copy file to staging
        staging = state.staging_dir / "mysource" / "file.txt"
        staging.parent.mkdir(parents=True)
        staging.write_text("backed up content")

        # Mock config
        class MockConfig:
            @property
            def sources(self):
                return [{"name": "mysource", "type": "directory", "path": str(src_dir)}]

        cfg = MockConfig()
        enc = Encryptor("test-key")
        restorer = Restorer(cfg, enc, state)
        manifest = EncryptManifest(state.encrypt_manifest_path)

        # Restore
        success = restorer.restore_file("mysource/file.txt", str(src_dir / "file.txt"), manifest)
        assert success
        assert (src_dir / "file.txt").read_text() == "backed up content"

    def test_restore_encrypted_file(self):
        """Test restoring an encrypted file with decryption."""
        src_dir = Path(tempfile.mkdtemp()) / "original2"
        src_dir.mkdir(parents=True)

        state_dir = Path(tempfile.mkdtemp()) / ".secret-global-backup2"
        state = State(state_dir)
        state.initialize()

        enc = Encryptor("restore-enc-key")
        original_content = b"super secret data for restore test"

        # Encrypt and put in staging
        staging_file = state.staging_dir / "mysource" / "secret.txt.enc"
        staging_file.parent.mkdir(parents=True)
        # Actually encrypt our content
        tmp = Path(tempfile.mktemp())
        tmp.write_bytes(original_content)
        encrypted = enc.encrypt_stream(tmp)
        staging_file.write_bytes(encrypted)
        tmp.unlink()

        # Add to manifest
        manifest = EncryptManifest(state.encrypt_manifest_path)
        manifest.add("mysource/secret.txt", "mysource/secret.txt.enc",
                      enc.salt_hex, "embedded")

        class MockConfig:
            @property
            def sources(self):
                return [{"name": "mysource", "type": "directory", "path": str(src_dir)}]

        cfg = MockConfig()
        restorer = Restorer(cfg, enc, state)

        # Restore should check .enc files when manifest says encrypted
        success = restorer.restore_file("mysource/secret.txt",
                                        str(src_dir / "secret.txt"), manifest)
        assert success
        assert (src_dir / "secret.txt").read_bytes() == original_content
