"""Tests for the encryption module."""

import os
import tempfile
from pathlib import Path

import pytest

from sgb.encryptor import Encryptor, EncryptorError, EncryptManifest, MAGIC_HEADER


class TestEncryptor:
    def test_encrypt_decrypt_bytes(self):
        enc = Encryptor("test-passphrase-123")
        data = b"Hello, this is secret data!"
        encrypted = enc.encrypt(data)
        # Encrypted data should be different from original
        assert encrypted != data
        # Should contain salt
        assert len(encrypted) > 32 + 12 + len(data)
        decrypted = enc.decrypt(encrypted)
        assert decrypted == data

    def test_different_ivs_produce_different_ciphertext(self):
        enc = Encryptor("test-passphrase-123")
        data = b"same data"
        c1 = enc.encrypt(data)
        c2 = enc.encrypt(data)
        # Different IVs should produce different ciphertexts
        assert c1 != c2

    def test_wrong_passphrase_fails(self):
        enc1 = Encryptor("correct-passphrase")
        data = b"secret"
        encrypted = enc1.encrypt(data)
        enc2 = Encryptor("wrong-passphrase")
        with pytest.raises(EncryptorError, match="Decryption failed"):
            enc2.decrypt(encrypted)

    def test_empty_passphrase_fails(self):
        with pytest.raises(EncryptorError, match="cannot be empty"):
            Encryptor("")

    def test_encrypt_stream(self):
        enc = Encryptor("test-key")
        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as f:
            f.write(b"File content to encrypt")
            f.flush()
            path = Path(f.name)

        try:
            encrypted = enc.encrypt_stream(path)
            assert encrypted.startswith(MAGIC_HEADER)
            # Should be magic header + salt + iv + ciphertext
            assert len(encrypted) > len(MAGIC_HEADER) + 32 + 12
        finally:
            path.unlink(missing_ok=True)

    def test_encrypt_decrypt_file(self):
        enc = Encryptor("file-passphrase")
        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as f:
            f.write(b"File content for roundtrip test")
            f.flush()
            src = Path(f.name)

        try:
            # Encrypt to file
            encrypted_data = enc.encrypt_stream(src)
            enc_file = Path(str(src) + ".enc")
            enc_file.write_bytes(encrypted_data)

            # Decrypt from file
            decrypted = enc.decrypt_file(enc_file)
            assert decrypted == b"File content for roundtrip test"
        finally:
            src.unlink(missing_ok=True)
            Path(str(src) + ".enc").unlink(missing_ok=True)

    def test_encrypt_to_file_and_decrypt_to_file(self):
        enc = Encryptor("another-key")
        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as f:
            f.write(b"Content for file-to-file test")
            f.flush()
            src = Path(f.name)

        dest = Path(str(src) + ".enc")
        out = Path(str(src) + ".dec")

        try:
            salt = enc.encrypt_to_file(src, dest)
            assert isinstance(salt, str)
            assert dest.exists()

            success = enc.decrypt_to_file(dest, out)
            assert success
            assert out.read_bytes() == b"Content for file-to-file test"
        finally:
            src.unlink(missing_ok=True)
            dest.unlink(missing_ok=True)
            out.unlink(missing_ok=True)

    def test_tampered_data_detected(self):
        enc = Encryptor("tamper-test")
        data = b"Important data"
        encrypted = enc.encrypt(data)
        # Tamper with the ciphertext
        tampered = bytearray(encrypted)
        tampered[-1] ^= 0xFF
        with pytest.raises(EncryptorError, match="Decryption failed"):
            enc.decrypt(bytes(tampered))

    def test_same_salt_same_key(self):
        salt = os.urandom(32)
        enc1 = Encryptor("same-pass", salt=salt)
        enc2 = Encryptor("same-pass", salt=salt)
        data = b"test data"
        c1 = enc1.encrypt(data)
        # With same key but different IVs, ciphertexts differ
        c2 = enc2.encrypt(data)
        assert c1 != c2
        # But both can decrypt each other's output (since salt matches)
        assert enc2.decrypt(c1) == data


class TestEncryptManifest:
    def test_add_and_get(self):
        path = Path(tempfile.mkdtemp()) / "encrypt_manifest.json"
        m = EncryptManifest(path)
        m.add("source/file.txt", "source/file.txt.enc", "abc123", "def456")
        entry = m.get("source/file.txt")
        assert entry["encrypted_path"] == "source/file.txt.enc"
        assert entry["salt"] == "abc123"
        assert entry["algorithm"] == "AES-256-GCM"

    def test_is_encrypted(self):
        path = Path(tempfile.mkdtemp()) / "encrypt_manifest.json"
        m = EncryptManifest(path)
        assert not m.is_encrypted("some/file.txt")
        m.add("some/file.txt", "some/file.txt.enc", "salt", "iv")
        assert m.is_encrypted("some/file.txt")

    def test_persistence(self):
        d = Path(tempfile.mkdtemp())
        path = d / "encrypt_manifest.json"
        m1 = EncryptManifest(path)
        m1.add("a.txt", "a.txt.enc", "salt1", "iv1")
        m1.save()

        m2 = EncryptManifest(path)
        assert m2.is_encrypted("a.txt")
        assert m2.get("a.txt")["salt"] == "salt1"

    def test_remove(self):
        path = Path(tempfile.mkdtemp()) / "encrypt_manifest.json"
        m = EncryptManifest(path)
        m.add("f.txt", "f.txt.enc", "s", "i")
        assert m.is_encrypted("f.txt")
        m.remove("f.txt")
        assert not m.is_encrypted("f.txt")
