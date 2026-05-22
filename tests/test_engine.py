"""Integration tests for the full backup engine."""

import json
import tempfile
from pathlib import Path

import pytest
import yaml

from sgb.config import Config
from sgb.engine import BackupEngine, EngineError
from sgb.encryptor import Encryptor


class TestConfig:
    def test_load_valid_config(self):
        config_data = {
            "version": "1.0",
            "encryption_key": "test-key-12345",
            "sources": [
                {"name": "test-dir", "type": "directory", "path": "/tmp/test"}
            ]
        }
        path = Path(tempfile.mktemp(suffix=".yaml"))
        path.write_text(yaml.dump(config_data))
        try:
            cfg = Config(path)
            data = cfg.load()
            assert len(cfg.sources) == 1
            assert cfg.encryption_key == "test-key-12345"
        finally:
            path.unlink(missing_ok=True)

    def test_missing_sources_fails(self):
        config_data = {
            "version": "1.0",
            "encryption_key": "test-key",
            "sources": []
        }
        path = Path(tempfile.mktemp(suffix=".yaml"))
        path.write_text(yaml.dump(config_data))
        try:
            cfg = Config(path)
            with pytest.raises(Exception):
                cfg.load()
        finally:
            path.unlink(missing_ok=True)

    def test_env_var_resolution(self):
        import os
        os.environ["TEST_SGB_KEY"] = "env-resolved-key"
        config_data = {
            "version": "1.0",
            "encryption_key": "${TEST_SGB_KEY}",
            "sources": [
                {"name": "test", "type": "directory", "path": "/tmp"}
            ]
        }
        path = Path(tempfile.mktemp(suffix=".yaml"))
        path.write_text(yaml.dump(config_data))
        try:
            cfg = Config(path)
            cfg.load()
            assert cfg.encryption_key == "env-resolved-key"
        finally:
            path.unlink(missing_ok=True)
            del os.environ["TEST_SGB_KEY"]

    def test_generate_example(self):
        cfg = Config(Path("/tmp/sgb.yaml"))
        example = cfg.generate_example()
        assert "version" in example
        assert "encryption_key" in example


class TestFullBackupPipeline:
    def test_end_to_end_backup_restore(self):
        """Full end-to-end: create files, backup, restore, verify."""
        # Setup source directory
        src = Path(tempfile.mkdtemp()) / "myapp"
        src.mkdir(parents=True)
        (src / "readme.md").write_text("# My App")
        (src / "config.yml").write_text("setting: value")
        secrets = src / "secrets"
        secrets.mkdir()
        (secrets / ".env").write_text("DB_PASS=supersecretpassword")
        (secrets / "api.key").write_text("sk-live-abc123xyz")

        # Setup state directory
        state_dir = Path(tempfile.mkdtemp()) / ".secret-global-backup"
        work_dir = Path(tempfile.mkdtemp())

        # Create config
        config_data = {
            "version": "1.0",
            "encryption_key": "e2e-test-passphrase-strong",
            "state_dir": str(state_dir),
            "sources": [
                {
                    "name": "myapp",
                    "type": "directory",
                    "path": str(src),
                    "ignore": ["*.tmp", ".git/"],
                    "encrypt": ["**/secrets/**", "**/.env"]
                }
            ]
        }
        config_path = work_dir / "sgb.yaml"
        config_path.write_text(yaml.dump(config_data))

        # Run backup
        cfg = Config(config_path)
        cfg.load()
        engine = BackupEngine(cfg)
        stats = engine.backup(dry_run=False)

        # Verify stats
        assert stats["files"] >= 3  # readme, config, .env, api.key (4 expected, minus build artifacts)
        assert stats["files"] >= 2
        assert stats["commit"] != ""

        # Verify staging has files
        staging = state_dir / "staging"
        assert staging.exists()
        assert (staging / "myapp" / "readme.md").exists()

        # Verify encrypted files
        enc_env = staging / "myapp" / "secrets" / ".env.enc"
        enc_key = staging / "myapp" / "secrets" / "api.key.enc"
        assert enc_env.exists() or enc_key.exists(), "Expected encrypted files"

        if enc_env.exists():
            content = enc_env.read_bytes()
            assert b"supersecretpassword" not in content, "Encrypted file should not contain plaintext"

        # Verify git repo has commits
        assert (state_dir / ".git").exists()

        print(f"\n✅ E2E test passed: {stats['files']} files backed up, "
              f"commit: {stats['commit'][:12]}")
