"""Database dump, backup, and restore.

Supports SQLite (built-in), PostgreSQL (pg_dump/pg_restore), and MySQL (mysqldump/mysql).
"""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from .encryptor import Encryptor, EncryptManifest


class DBError(Exception):
    """Database operation error."""


def dump_sqlite(db_path: Path, output_path: Path) -> Path:
    """Dump SQLite database to a file. Simple file copy since SQLite is single-file."""
    if not db_path.exists():
        raise DBError(f"SQLite database not found: {db_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(db_path, output_path)
    return output_path


def restore_sqlite(backup_path: Path, target_path: Path) -> Path:
    """Restore SQLite database from backup file."""
    if not backup_path.exists():
        raise DBError(f"Backup file not found: {backup_path}")
    target_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(backup_path, target_path)
    return target_path


def dump_postgres(host: str, port: int, database: str, user: str,
                  password: str, output_path: Path) -> Path:
    """Dump PostgreSQL database using pg_dump."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["PGPASSWORD"] = password
    cmd = [
        "pg_dump",
        "-h", host,
        "-p", str(port),
        "-U", user,
        "-d", database,
        "-F", "c",  # Custom format
        "-f", str(output_path),
    ]
    result = subprocess.run(cmd, env=env, capture_output=True, text=True)
    if result.returncode != 0:
        raise DBError(f"pg_dump failed: {result.stderr}")
    return output_path


def restore_postgres(host: str, port: int, database: str, user: str,
                     password: str, backup_path: Path) -> bool:
    """Restore PostgreSQL database using pg_restore."""
    if not backup_path.exists():
        raise DBError(f"Backup file not found: {backup_path}")
    env = os.environ.copy()
    env["PGPASSWORD"] = password
    cmd = [
        "pg_restore",
        "-h", host,
        "-p", str(port),
        "-U", user,
        "-d", database,
        "-c",  # Clean (drop) before restore
        "--if-exists",
        str(backup_path),
    ]
    result = subprocess.run(cmd, env=env, capture_output=True, text=True)
    if result.returncode != 0:
        raise DBError(f"pg_restore failed: {result.stderr}")
    return True


def dump_mysql(host: str, port: int, database: str, user: str,
               password: str, output_path: Path) -> Path:
    """Dump MySQL database using mysqldump."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "mysqldump",
        "-h", host,
        "-P", str(port),
        "-u", user,
        f"--password={password}",
        "--single-transaction",
        "--routines",
        "--triggers",
        database,
    ]
    with open(output_path, "w") as f:
        result = subprocess.run(cmd, stdout=f, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        raise DBError(f"mysqldump failed: {result.stderr}")
    return output_path


def restore_mysql(host: str, port: int, database: str, user: str,
                  password: str, backup_path: Path) -> bool:
    """Restore MySQL database from dump file."""
    if not backup_path.exists():
        raise DBError(f"Backup file not found: {backup_path}")
    cmd = [
        "mysql",
        "-h", host,
        "-P", str(port),
        "-u", user,
        f"--password={password}",
        database,
    ]
    with open(backup_path) as f:
        result = subprocess.run(cmd, stdin=f, capture_output=True, text=True)
    if result.returncode != 0:
        raise DBError(f"mysql restore failed: {result.stderr}")
    return True


class DBHandler:
    """Handles database backups as part of the SGB pipeline."""

    def __init__(self, encryptor: Encryptor, staging_dir: Path):
        self.encryptor = encryptor
        self.staging_dir = staging_dir

    def dump_source(self, source: dict, encrypt_manifest: EncryptManifest) -> Optional[str]:
        """Dump a database source. Returns the staging filename or None on skip."""
        db_type = source["type"]
        name = source.get("name", f"db-{db_type}")
        should_encrypt = source.get("encrypt", False)
        if isinstance(should_encrypt, list) and len(should_encrypt) > 0:
            should_encrypt = True

        db_dir = self.staging_dir / "_databases"
        db_dir.mkdir(parents=True, exist_ok=True)

        if db_type == "sqlite":
            db_path = Path(source["path"])
            output = db_dir / f"{name}.db"
            dump_sqlite(db_path, output)
        elif db_type == "postgres":
            output = db_dir / f"{name}.pgdump"
            dump_postgres(
                host=source.get("host", "localhost"),
                port=source.get("port", 5432),
                database=source["database"],
                user=source["user"],
                password=source.get("password", ""),
                output_path=output,
            )
        elif db_type == "mysql":
            output = db_dir / f"{name}.sql"
            dump_mysql(
                host=source.get("host", "localhost"),
                port=source.get("port", 3306),
                database=source["database"],
                user=source["user"],
                password=source.get("password", ""),
                output_path=output,
            )
        else:
            raise DBError(f"Unsupported database type: {db_type}")

        staging_name = f"_databases/{output.name}"

        if should_encrypt:
            encrypted = self.encryptor.encrypt_stream(output)
            enc_output = Path(str(output) + ".enc")
            enc_output.write_bytes(encrypted)
            output.unlink()  # Remove plaintext
            encrypt_manifest.add(
                original_path=staging_name,
                encrypted_path=f"{staging_name}.enc",
                salt_hex=self.encryptor.salt_hex,
                iv_hex="embedded",
            )
            return f"{staging_name}.enc"
        return staging_name
