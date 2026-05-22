"""Tests for the packager module."""

import tempfile
from pathlib import Path

import pytest

from sgb.config import Config
from sgb.encryptor import Encryptor, EncryptManifest


class TestPackager:
    def test_should_ignore(self):
        """Test ignore pattern matching."""
        from sgb.packager import Packager
        pkg = Packager(None, None, Path("/tmp"))
        
        # Default ignores
        assert pkg.should_ignore(".git/config", [])
        assert pkg.should_ignore("__pycache__/module.pyc", [])
        assert pkg.should_ignore("something/.DS_Store", [])
        
        # Custom ignores
        assert pkg.should_ignore("node_modules/package/index.js", ["node_modules/"])
        assert pkg.should_ignore("app.log", ["*.log"])
        assert pkg.should_ignore("build/output.o", ["build/"])
        
        # Non-matches
        assert not pkg.should_ignore("src/main.py", [])
        assert not pkg.should_ignore("README.md", ["*.log"])

    def test_should_encrypt(self):
        """Test encryption pattern matching."""
        from sgb.packager import Packager
        pkg = Packager(None, None, Path("/tmp"))
        
        patterns = ["**/secrets/**", "**/.env", "**/credentials.*"]
        
        assert pkg.should_encrypt("secrets/api-keys.txt", patterns)
        assert pkg.should_encrypt("project/secrets/nested/key.txt", patterns)
        assert pkg.should_encrypt(".env", patterns)
        assert pkg.should_encrypt("subdir/.env", patterns)
        assert pkg.should_encrypt("credentials.json", patterns)
        
        # Non-matches
        assert not pkg.should_encrypt("src/main.py", patterns)
        assert not pkg.should_encrypt("README.md", patterns)

    def test_package_directory_basic(self):
        """Test basic directory packaging without encryption."""
        import shutil
        from sgb.packager import Packager
        
        # Create temp source directory
        src = Path(tempfile.mkdtemp()) / "test_src"
        src.mkdir()
        (src / "readme.txt").write_text("hello")
        (src / "data.json").write_text('{"a":1}')
        sub = src / "sub"
        sub.mkdir()
        (sub / "notes.md").write_text("notes")
        
        # Create temp staging
        staging = Path(tempfile.mkdtemp()) / "staging"
        staging.mkdir(parents=True)
        
        # Mock config
        class MockConfig:
            def get_ignore_patterns(self, name): return []
            def get_encrypt_patterns(self, name): return []
            @property
            def sources(self):
                return [{"name": "test", "type": "directory", "path": str(src)}]
        
        enc = Encryptor("test-key")
        cfg = MockConfig()
        pkg = Packager(cfg, enc, staging)
        
        manifest = EncryptManifest(Path(tempfile.mkdtemp()) / "enc.json")
        stats = pkg.collect_all_sources(manifest)
        
        assert stats["files"] == 3
        assert (staging / "test" / "readme.txt").exists()
        assert (staging / "test" / "data.json").exists()
        assert (staging / "test" / "sub" / "notes.md").exists()
        
        # Cleanup
        shutil.rmtree(src.parent, ignore_errors=True)
        shutil.rmtree(staging.parent, ignore_errors=True)

    def test_package_directory_with_encryption(self):
        """Test packaging with file encryption."""
        import shutil
        from sgb.packager import Packager
        
        src = Path(tempfile.mkdtemp()) / "test_src2"
        src.mkdir()
        (src / "normal.txt").write_text("public content")
        secrets = src / "secrets"
        secrets.mkdir()
        (secrets / "key.txt").write_text("super-secret-key")
        
        staging = Path(tempfile.mkdtemp()) / "staging2"
        staging.mkdir(parents=True)
        
        class MockConfig:
            def get_ignore_patterns(self, name): return ["*.log"]
            def get_encrypt_patterns(self, name): return ["**/secrets/**"]
            @property
            def sources(self):
                return [{"name": "test2", "type": "directory", "path": str(src)}]
        
        enc = Encryptor("enc-test-key")
        cfg = MockConfig()
        pkg = Packager(cfg, enc, staging)
        
        manifest = EncryptManifest(Path(tempfile.mkdtemp()) / "enc2.json")
        stats = pkg.collect_all_sources(manifest)
        
        assert stats["files"] == 2
        assert stats["encrypted"] == 1
        
        # Normal file should be plain
        assert (staging / "test2" / "normal.txt").exists()
        assert (staging / "test2" / "normal.txt").read_text() == "public content"
        
        # Secret file should be encrypted
        enc_file = staging / "test2" / "secrets" / "key.txt.enc"
        assert enc_file.exists()
        encrypted_content = enc_file.read_bytes()
        assert b"super-secret-key" not in encrypted_content  # Shouldn't be plaintext
        
        # Should be decryptable
        decrypted = enc.decrypt_file(enc_file)
        assert decrypted == b"super-secret-key"
        
        # Manifest should have the entry
        assert manifest.is_encrypted("test2/secrets/key.txt")
        
        shutil.rmtree(src.parent, ignore_errors=True)
        shutil.rmtree(staging.parent, ignore_errors=True)
