"""Test fixture generation."""

import os
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def create_sample_project():
    """Create a sample project directory tree for testing."""
    root = FIXTURES_DIR / "sample_project"
    root.mkdir(parents=True, exist_ok=True)

    # Normal files
    (root / "README.md").write_text("# Sample Project\n\nThis is a test project.")
    (root / "config.yaml").write_text("database:\n  host: localhost\n  port: 5432\n")

    # Nested subdirectory
    subdir = root / "subdir"
    subdir.mkdir(exist_ok=True)
    (subdir / "notes.txt").write_text("These are important notes.")
    (subdir / "data.json").write_text('{"key": "value"}')

    # Secrets directory (should be encrypted)
    secrets = root / "secrets"
    secrets.mkdir(exist_ok=True)
    (secrets / "api-keys.txt").write_text("API_KEY=sk-1234567890abcdef\nSECRET_TOKEN=ghp_secret123")
    (secrets / "credentials.json").write_text('{"username": "admin", "password": "super_secret_123"}')
    nested_secrets = secrets / "nested"
    nested_secrets.mkdir(exist_ok=True)
    (nested_secrets / ".env").write_text("DATABASE_URL=postgresql://user:pass@localhost/db")

    # Build directory (should be ignored)
    build = root / "build"
    build.mkdir(exist_ok=True)
    (build / "output.o").write_text("binary data here")
    (build / "temp.cache").write_text("cache data")

    # Node modules (should be ignored)
    node_modules = root / "node_modules"
    node_modules.mkdir(exist_ok=True)
    (node_modules / "package.json").write_text('{"name": "test-package"}')
    (node_modules / "index.js").write_text("module.exports = {};")

    print(f"Created sample project at: {root}")
    return root


def create_sample_sqlite_db():
    """Create a sample SQLite database."""
    import sqlite3
    db_path = FIXTURES_DIR / "test.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT, email TEXT)")
    conn.execute("INSERT INTO users VALUES (1, 'Alice', 'alice@example.com')")
    conn.execute("INSERT INTO users VALUES (2, 'Bob', 'bob@example.com')")
    conn.execute("INSERT INTO users VALUES (3, 'Charlie', 'charlie@example.com')")
    conn.execute("CREATE TABLE secrets (id INTEGER PRIMARY KEY, key TEXT, value TEXT)")
    conn.execute("INSERT INTO secrets VALUES (1, 'api_key', 'sk-top-secret-12345')")
    conn.commit()
    conn.close()
    print(f"Created sample SQLite DB at: {db_path}")
    return db_path


if __name__ == "__main__":
    create_sample_project()
    create_sample_sqlite_db()
