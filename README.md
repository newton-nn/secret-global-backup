# Secret Global Backup (SGB)

A configurable auto-backup system that provides:
- **DB data dump, backup and restore** (SQLite, PostgreSQL, MySQL)
- **Folder tree packaging** with ignore patterns and AES-256-GCM encryption
- **Git-based versioning** for incremental, efficient backups
- **Push to remote** (GitHub) at configurable intervals
- **Multi-location backup** from different directories
- **Restore to original locations** on demand
- **.secret-global-backup** hidden state directory (analogous to `.git`)

## Quick Start

```bash
pip install secret-global-backup
```

### 1. Initialize
```bash
sgb init --key "your-strong-passphrase"
```

### 2. Configure
Edit `sgb.yaml`:

```yaml
version: "1.0"
encryption_key: "${SGB_KEY}"  # or passphrase directly
remote:
  url: "git@github.com:you/backup-repo.git"
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
      - "**/credentials.*"

  - name: "app-db"
    type: sqlite
    path: "/var/lib/app/data.db"
    encrypt: true
```

### 3. Backup
```bash
# One-time backup
sgb backup

# Start scheduled backups (daemon mode)
sgb backup --daemon

# Backup with custom config
sgb backup --config /path/to/sgb.yaml
```

### 4. Restore
```bash
# List available versions
sgb versions

# Restore latest
sgb restore

# Restore specific version
sgb restore --version abc123

# Restore to different location
sgb restore --target /tmp/restored
```

## Architecture

```
.secret-global-backup/
├── repo/                  # Git repository for versioning
├── staging/               # Current staging area
├── manifest.json          # File tracking (path → hash, encryption status)
├── encrypt_manifest.json  # Encryption metadata (IVs, auth tags)
└── state.json             # Last backup timestamp, current version
```

## Encryption

- **AES-256-GCM**: Authenticated encryption with integrity verification
- **PBKDF2 key derivation**: Keys derived from passphrase with salt
- **Per-file encryption**: Each file encrypted independently with unique IV
- **Ignore then encrypt**: Ignore patterns applied first, encryption on remaining matches

## CLI Commands

| Command | Description |
|---------|-------------|
| `sgb init` | Initialize a new backup configuration |
| `sgb backup` | Run a backup (or start daemon with `--daemon`) |
| `sgb restore` | Restore files to original locations |
| `sgb versions` | List available backup versions |
| `sgb status` | Show current backup state |
| `sgb key rotate` | Rotate encryption key and re-encrypt |
| `sgb remote` | Manage remote repository |
| `sgb db dump` | Dump a database without backup |
| `sgb db restore` | Restore a database from backup |
