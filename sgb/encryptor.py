"""AES-256-GCM encryption and decryption module.

Uses PBKDF2 for key derivation from passphrase.
Each file gets a unique 96-bit IV (nonce).
Authenticated encryption prevents tampering.
"""

import os
import json
import hashlib
from pathlib import Path
from typing import Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend


SALT_SIZE = 32
IV_SIZE = 12  # 96 bits for GCM
KEY_SIZE = 32  # 256 bits
PBKDF2_ITERATIONS = 600_000
AUTH_TAG_SIZE = 16

# Magic header to identify encrypted files: SGB\x01
MAGIC_HEADER = b"SGB\x01"


class EncryptorError(Exception):
    """Encryption/decryption error."""


class Encryptor:
    """Handles AES-256-GCM encryption with PBKDF2 key derivation."""

    def __init__(self, passphrase: str, salt: Optional[bytes] = None):
        if not passphrase:
            raise EncryptorError("Encryption passphrase cannot be empty.")
        self._passphrase = passphrase.encode("utf-8")
        self._salt = salt if salt else os.urandom(SALT_SIZE)
        self._key = self._derive_key()

    def _derive_key(self) -> bytes:
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=KEY_SIZE,
            salt=self._salt,
            iterations=PBKDF2_ITERATIONS,
            backend=default_backend(),
        )
        return kdf.derive(self._passphrase)

    @property
    def salt(self) -> bytes:
        return self._salt

    @property
    def salt_hex(self) -> str:
        return self._salt.hex()

    def encrypt(self, data: bytes) -> bytes:
        """Encrypt data. Returns: salt(32) + iv(12) + ciphertext+tag."""
        iv = os.urandom(IV_SIZE)
        aesgcm = AESGCM(self._key)
        ciphertext = aesgcm.encrypt(iv, data, None)
        return self._salt + iv + ciphertext

    def encrypt_stream(self, filepath: Path) -> bytes:
        """Read and encrypt a file. Returns encrypted blob with header."""
        with open(filepath, "rb") as f:
            data = f.read()
        encrypted = self.encrypt(data)
        return MAGIC_HEADER + encrypted

    def decrypt(self, encrypted_data: bytes) -> bytes:
        """Decrypt data. Accepts salt+iv+ciphertext or just iv+ciphertext."""
        # Check if salt is prepended (at least SALT_SIZE + IV_SIZE)
        if len(encrypted_data) >= SALT_SIZE + IV_SIZE + AUTH_TAG_SIZE:
            salt = encrypted_data[:SALT_SIZE]
            iv = encrypted_data[SALT_SIZE:SALT_SIZE + IV_SIZE]
            ciphertext = encrypted_data[SALT_SIZE + IV_SIZE:]
            # Re-derive key with this salt
            kdf_key = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=KEY_SIZE,
                salt=salt,
                iterations=PBKDF2_ITERATIONS,
                backend=default_backend(),
            ).derive(self._passphrase)
        else:
            raise EncryptorError("Invalid encrypted data: too short")

        aesgcm = AESGCM(kdf_key)
        try:
            return aesgcm.decrypt(iv, ciphertext, None)
        except Exception as e:
            raise EncryptorError(f"Decryption failed: {e}. Wrong passphrase or corrupted data.")

    def decrypt_file(self, filepath: Path) -> bytes:
        """Read and decrypt a file, stripping the magic header if present."""
        with open(filepath, "rb") as f:
            data = f.read()
        if data.startswith(MAGIC_HEADER):
            data = data[len(MAGIC_HEADER):]
        return self.decrypt(data)

    def encrypt_to_file(self, source: Path, dest: Path) -> str:
        """Encrypt source file and write to dest. Returns hex-encoded IV."""
        encrypted = self.encrypt_stream(source)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "wb") as f:
            f.write(encrypted)
        return self.salt_hex

    def decrypt_to_file(self, source: Path, dest: Path) -> bool:
        """Decrypt source file and write to dest. Returns True on success."""
        try:
            decrypted = self.decrypt_file(source)
            dest.parent.mkdir(parents=True, exist_ok=True)
            with open(dest, "wb") as f:
                f.write(decrypted)
            return True
        except EncryptorError:
            return False


class EncryptManifest:
    """Tracks which files are encrypted and their encryption metadata."""

    def __init__(self, path: Path):
        self.path = path
        self.entries: dict = {}
        self._load()

    def _load(self):
        if self.path.exists():
            with open(self.path) as f:
                self.entries = json.load(f)

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w") as f:
            json.dump(self.entries, f, indent=2, sort_keys=True)

    def add(self, original_path: str, encrypted_path: str, salt_hex: str, iv_hex: str):
        self.entries[original_path] = {
            "encrypted_path": encrypted_path,
            "salt": salt_hex,
            "iv": iv_hex,
            "algorithm": "AES-256-GCM",
        }
        self.save()

    def get(self, original_path: str) -> Optional[dict]:
        return self.entries.get(original_path)

    def is_encrypted(self, original_path: str) -> bool:
        return original_path in self.entries

    def remove(self, original_path: str):
        if original_path in self.entries:
            del self.entries[original_path]
            self.save()

    def __iter__(self):
        return iter(self.entries.items())
