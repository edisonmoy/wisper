import logging
import subprocess
from pathlib import Path

logger = logging.getLogger("wisper")

# Guard against a compromised or redirected git remote.  Only HTTPS GitHub
# URLs are considered trustworthy for auto-install.
_TRUSTED_REMOTE_HOST = "github.com"


def _git(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git"] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=15,
    )


def _remote_is_trusted(repo_dir: Path) -> bool:
    """Return True only if origin resolves to a github.com URL."""
    r = _git(["remote", "get-url", "origin"], repo_dir)
    if r.returncode != 0:
        logger.error("Update check: 'git remote get-url origin' failed: %s", r.stderr.strip())
        return False
    url = r.stdout.strip()
    if _TRUSTED_REMOTE_HOST not in url:
        logger.error("Update check: origin remote %r is not a trusted GitHub URL", url)
        return False
    return True


def check_for_updates(repo_dir: Path) -> int:
    """Fetch origin/main and return number of new commits. -1 on error."""
    try:
        r = _git(["fetch", "origin", "main"], repo_dir)
        if r.returncode != 0:
            logger.error("Update check: 'git fetch origin main' failed: %s", r.stderr.strip())
            return -1
        r = _git(["rev-list", "HEAD..origin/main", "--count"], repo_dir)
        if r.returncode != 0:
            logger.error("Update check: 'git rev-list' failed: %s", r.stderr.strip())
            return -1
        n = int(r.stdout.strip())
        logger.info("Update check: %d new commit(s) on origin/main", n)
        return n
    except Exception as exc:
        logger.error("Update check failed: %s", exc)
        return -1


def install_update(repo_dir: Path) -> bool:
    """Pull latest code and sync venv deps. Returns True on success."""
    try:
        if not _remote_is_trusted(repo_dir):
            return False
        r = _git(["pull", "origin", "main"], repo_dir)
        if r.returncode != 0:
            logger.error("Update install: 'git pull origin main' failed: %s", r.stderr.strip())
            return False
        logger.info("Update install: pulled latest code from origin/main")
        pip = repo_dir / ".venv" / "bin" / "pip"
        if pip.exists():
            subprocess.run(
                [str(pip), "install", "-q", "-r", str(repo_dir / "requirements.txt")],
                timeout=120,
                check=False,
            )
            logger.info("Update install: synced dependencies")
        return True
    except Exception as exc:
        logger.error("Update install failed: %s", exc)
        return False
