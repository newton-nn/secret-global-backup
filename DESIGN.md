# Secret Global Backup - Architecture Design

## Overview
A configurable auto-backup system that uses git for versioning and AES-256-GCM for encryption.
The system maintains a `.secret-global-backup` hidden directory (analogous to `.git`) for state tracking,
and pushes encrypted backups to GitHub at configurable intervals.

## Architecture

```
secret-global-backup/
├── sgb/                    # Core package
│   ├── __init__.py
│   ├── cli.py              # CLI entrypoint (click/argparse)
│   ├── config.py           # Config loader/validator
│   ├── engine.py           # Core backup engine
│   ├── encryptor.py        # AES-256-GCM encryption/decryption
│   ├── db.py               # DB dump/restore (SQLite, PostgreSQL, MySQL)
│   ├── packager.py         # Folder tree packaging with ignore/encrypt specs
│   ├── remote.py           # Git remote push/pull operations
│   ├── restore.py          # Restore to original locations
│   ├── state.py            # .secret-global-backup state management
│   ├── scheduler.py        # Interval-based scheduling
│   └── versioning.py       # Git-based version management
├── tests/                  # Test suite
│   ├── test_encryptor.py
│   ├── test_engine.py
│   ├── test_db.py
│   ├── test_packager.py
│   ├── test_restore.py
│   └── fixtures/           # Test data
├── sgb.yaml.example        # Example config
├── setup.py / pyproject.toml
├── README.md
└── requirements.txt
```

## Data Flow

### Backup Flow
1. User runs `sgb backup` or scheduler triggers
2. Config loaded → sources, ignore patterns, encrypt patterns, remote
3. For each source:
   a. **DB sources**: Dump to temp file, encrypt if specified
   b. **Directory sources**: Walk tree, apply ignore patterns, encrypt matching files
4. All processed files placed in `.secret-global-backup/staging/`
5. Git commit in `.secret-global-backup/repo/` with version metadata
6. Push to remote if configured

### Restore Flow
1. User runs `sgb restore [--version V] [--target PATH]`
2. Git checkout requested version from `.secret-global-backup/repo/`
3. Decrypt encrypted files using stored key
4. Copy/restore files to original locations (or specified target)

## Key Design Decisions

### Built on Git
- Uses git internally for versioning, delta compression, and remote push
- The `.secret-global-backup/repo/` is a bare git repo
- Each backup creates a commit with structured metadata

### Encryption Strategy
- AES-256-GCM (authenticated encryption)
- Key derived from user-provided passphrase via PBKDF2
- Each file encrypted independently (parallel-friendly)
- Encrypted files stored with `.enc` extension
- Encryption manifest maps original paths → encrypted paths + IV + tag

### Ignore System
- `.sgbignore` file per source directory (gitignore-compatible syntax)
- Also supports inline patterns in config
- Applied BEFORE encryption (ignore first, encrypt remaining)

### Config Structure
```yaml
version: "1.0"
encryption_key: "${SGB_KEY}"  # or inline passphrase
remote:
  url: "git@github.com:user/backup-repo.git"
  branch: "main"
schedule:
  interval_minutes: 60
sources:
  - name: "project-files"
    type: directory
    path: "/home/user/projects"
    ignore:
      - "node_modules/"
      - "*.log"
      - ".git/"
    encrypt:
      - "**/secrets/**"
      - "**/.env"
      - "**/credentials.json"

  - name: "postgres-db"
    type: postgres
    host: "localhost"
    port: 5432
    database: "myapp"
    user: "backup_user"
    password: "${DB_PASS}"
    encrypt: true

  - name: "sqlite-db"
    type: sqlite
    path: "/var/lib/app/data.db"
    encrypt: true
```

### State Directory Layout
```
.secret-global-backup/
├── repo/                  # Git repository (bare)
├── staging/               # Current staging area
├── manifest.json          # File manifest (path → hash, encrypted status)
├── encrypt_manifest.json  # Encryption metadata (IVs, tags)
├── state.json             # Current state (last backup timestamp, version)
└── keyfile.enc            # Encrypted key storage (optional)
```
