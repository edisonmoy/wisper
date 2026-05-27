import subprocess
from pathlib import Path


def _git(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ['git'] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=15,
    )


def check_for_updates(repo_dir: Path) -> int:
    """Fetch origin/main and return number of new commits. -1 on error."""
    try:
        if _git(['fetch', 'origin', 'main'], repo_dir).returncode != 0:
            return -1
        r = _git(['rev-list', 'HEAD..origin/main', '--count'], repo_dir)
        if r.returncode != 0:
            return -1
        return int(r.stdout.strip())
    except Exception:
        return -1


def install_update(repo_dir: Path) -> bool:
    """Pull latest code and sync venv deps. Returns True on success."""
    try:
        if _git(['pull', 'origin', 'main'], repo_dir).returncode != 0:
            return False
        pip = repo_dir / '.venv' / 'bin' / 'pip'
        if pip.exists():
            subprocess.run(
                [str(pip), 'install', '-q', '-r', str(repo_dir / 'requirements.txt')],
                timeout=120,
                check=False,
            )
        return True
    except Exception:
        return False
