"""Tests for database operations."""

import sqlite3
import tempfile
from pathlib import Path

import pytest

from sgb.db import dump_sqlite, restore_sqlite, DBError


class TestSQLite:
    def test_dump_sqlite(self):
        # Create a test SQLite DB
        db_path = Path(tempfile.mktemp(suffix=".db"))
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE test (id INTEGER, name TEXT)")
        conn.execute("INSERT INTO test VALUES (1, 'hello')")
        conn.commit()
        conn.close()

        output = Path(tempfile.mktemp(suffix=".db"))
        try:
            result = dump_sqlite(db_path, output)
            assert result.exists()
            assert result.stat().st_size > 0

            # Verify dump has our data
            conn2 = sqlite3.connect(str(output))
            rows = conn2.execute("SELECT * FROM test").fetchall()
            assert rows == [(1, "hello")]
            conn2.close()
        finally:
            db_path.unlink(missing_ok=True)
            output.unlink(missing_ok=True)

    def test_dump_nonexistent_db(self):
        with pytest.raises(DBError, match="not found"):
            dump_sqlite(Path("/nonexistent/path.db"), Path("/tmp/out.db"))

    def test_restore_sqlite(self):
        # Create source
        src = Path(tempfile.mktemp(suffix=".db"))
        conn = sqlite3.connect(str(src))
        conn.execute("CREATE TABLE data (key TEXT, value TEXT)")
        conn.execute("INSERT INTO data VALUES ('name', 'Alice')")
        conn.commit()
        conn.close()

        backup = Path(tempfile.mktemp(suffix=".db"))
        dump_sqlite(src, backup)

        # Restore to new location
        target = Path(tempfile.mktemp(suffix=".db"))
        try:
            result = restore_sqlite(backup, target)
            assert result.exists()

            conn3 = sqlite3.connect(str(target))
            rows = conn3.execute("SELECT * FROM data").fetchall()
            assert rows == [("name", "Alice")]
            conn3.close()
        finally:
            src.unlink(missing_ok=True)
            backup.unlink(missing_ok=True)
            target.unlink(missing_ok=True)

    def test_restore_nonexistent_backup(self):
        with pytest.raises(DBError, match="not found"):
            restore_sqlite(Path("/nonexistent/backup.db"), Path("/tmp/target.db"))
