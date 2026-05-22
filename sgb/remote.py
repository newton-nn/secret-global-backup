"""Git-based remote operations for pushing/pulling backups."""

import os
import subprocess
from pathlib import Path
from typing import List, Optional


class RemoteError(Exception):
    """Remote operation error."""


class Remote:
    """Manages git remote operations for the backup repository."""

    def __init__(self, repo_dir: Path):
        self.repo_dir = repo_dir

    def _git(self, *args, cwd: Optional[Path] = None) -> subprocess.CompletedProcess:
        """Run a git command in the repo directory."""
        cwd = cwd or self.repo_dir
        cmd = ["git", "-C", str(cwd)] + list(args)
        result = subprocess.run(cmd, capture_output=True, text=True)
        return result

    def init_repo(self) -> bool:
        """Initialize the git repository. Returns True if new, False if already exists."""
        git_dir = self.repo_dir / ".git"
        if git_dir.exists():
            return False
        self.repo_dir.mkdir(parents=True, exist_ok=True)
        result = self._git("init")
        if result.returncode != 0:
            raise RemoteError(f"Git init failed: {result.stderr}")
        # Configure git user for commits
        self._git("config", "user.email", "sgb@backup.local")
        self._git("config", "user.name", "Secret Global Backup")
        return True

    def is_initialized(self) -> bool:
        return (self.repo_dir / ".git").exists()

    def add_remote(self, url: str, name: str = "origin") -> bool:
        """Add a remote. Returns True if added, False if already exists."""
        result = self._git("remote", "get-url", name)
        if result.returncode == 0:
            current = result.stdout.strip()
            if current != url:
                self._git("remote", "set-url", name, url)
            return False
        result = self._git("remote", "add", name, url)
        if result.returncode != 0:
            raise RemoteError(f"Failed to add remote: {result.stderr}")
        return True

    def has_remote(self, name: str = "origin") -> bool:
        result = self._git("remote", "get-url", name)
        return result.returncode == 0

    def commit(self, message: str) -> str:
        """Stage all files and commit. Returns commit hash."""
        # Stage all
        result = self._git("add", "-A")
        if result.returncode != 0:
            raise RemoteError(f"Git add failed: {result.stderr}")

        # Check if there's anything to commit
        status = self._git("status", "--porcelain")
        if not status.stdout.strip():
            return ""  # Nothing to commit

        result = self._git("commit", "-m", message)
        if result.returncode != 0:
            raise RemoteError(f"Git commit failed: {result.stderr}")

        # Get commit hash
        hash_result = self._git("rev-parse", "HEAD")
        return hash_result.stdout.strip()

    def push(self, remote: str = "origin", branch: str = "main") -> bool:
        """Push to remote. Returns True on success."""
        result = self._git("push", "-u", remote, branch)
        if result.returncode != 0:
            # Check if it's just "everything up-to-date"
            if "Everything up-to-date" in result.stderr or "up to date" in result.stdout:
                return True
            raise RemoteError(f"Git push failed: {result.stderr}\n{result.stdout}")
        return True

    def pull(self, remote: str = "origin", branch: str = "main") -> bool:
        """Pull from remote. Returns True on success."""
        result = self._git("pull", remote, branch)
        if result.returncode != 0:
            raise RemoteError(f"Git pull failed: {result.stderr}")
        return True

    def get_log(self, max_count: int = 20) -> List[dict]:
        """Get commit log."""
        if not self.is_initialized():
            return []
        result = self._git(
            "log",
            f"--max-count={max_count}",
            "--format=%H|%ai|%s",
        )
        if result.returncode != 0:
            return []
        entries = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            parts = line.split("|", 2)
            if len(parts) == 3:
                entries.append({
                    "hash": parts[0],
                    "date": parts[1],
                    "message": parts[2],
                })
        return entries

    def checkout(self, commit_hash: str) -> bool:
        """Checkout a specific commit."""
        result = self._git("checkout", commit_hash)
        if result.returncode != 0:
            raise RemoteError(f"Git checkout failed: {result.stderr}")
        return True

    def checkout_latest(self) -> bool:
        """Checkout the latest commit on current branch."""
        result = self._git("checkout", "main")
        if result.returncode != 0:
            raise RemoteError(f"Git checkout main failed: {result.stderr}")
        return True

    def get_current_hash(self) -> Optional[str]:
        """Get current HEAD commit hash."""
        result = self._git("rev-parse", "HEAD")
        if result.returncode != 0:
            return None
        return result.stdout.strip()

    def clone(self, url: str, target: Path) -> bool:
        """Clone a remote repository."""
        if target.exists():
            raise RemoteError(f"Target directory already exists: {target}")
        result = subprocess.run(
            ["git", "clone", url, str(target)],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            raise RemoteError(f"Git clone failed: {result.stderr}")
        return True
