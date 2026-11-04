import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path

def _run(cmd: list[str], cwd: Path, timeout: int = 30) -> tuple[int, str, str]:
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "TIMEOUT"
    except FileNotFoundError as e:
        return -2, "", str(e)


@dataclass
class CommitResult:
    committed: bool
    sha: str = ""
    branch: str = ""
    message: str = ""

def ensure_repo(sandbox: Path, base: str = "main") -> bool:
    """Init git in sandbox if needed and ensure a base branch exists.
    Returns True if anything had to be created."""
    sandbox = sandbox.resolve()
    changed = False

    if not (sandbox / ".git").exists():
        _run(["git", "init", "-b", base], sandbox)
        changed = True

    _run(["git", "config", "user.email", "harny@local"], sandbox)
    _run(["git", "config", "user.name", "Harny"], sandbox)
    _run(["git", "config", "core.autocrlf", "false"], sandbox)

    rc, _, _ = _run(["git", "rev-parse", "--verify", base], sandbox)
    if rc != 0:
        rc2, _, err2 = _run(
            ["git", "commit", "--allow-empty", "-m", "init: empty base"],
            sandbox,
        )
        if rc2 != 0:
            raise RuntimeError(f"could not create base commit: {err2}")
        current = current_branch(sandbox)
        if current != base:
            _run(["git", "branch", "-m", current, base], sandbox)
        changed = True

    _run(["git", "checkout", base], sandbox)

    return changed

def create_branch(sandbox: Path, name: str, base: str = "main") -> str:
    """Create and check out a new branch from base. Returns the branch name."""
    rc, _, err = _run(["git", "checkout", "-b", name, base], sandbox)
    if rc != 0:
        raise RuntimeError(f"git checkout -b {name} failed: {err}")
    return name

def commit_all(sandbox: Path, message: str) -> CommitResult:
    """Stage everything and commit. No-op if working tree is clean."""
    _run(["git", "add", "-A"], sandbox)

    rc, out, _ = _run(["git", "status", "--porcelain"], sandbox)
    if not out.strip():
        return CommitResult(committed=False, branch=current_branch(sandbox))

    rc, _, err = _run(["git", "commit", "-m", message], sandbox)
    if rc != 0:
        raise RuntimeError(f"git commit failed: {err}")

    _, sha_out, _ = _run(["git", "rev-parse", "HEAD"], sandbox)
    return CommitResult(
        committed=True,
        sha=sha_out.strip(),
        branch=current_branch(sandbox),
        message=message,
    )

def diff_against(sandbox: Path, base: str = "main", head: str = "HEAD") -> str:
    rc, out, err = _run(["git", "diff", f"{base}..{head}"], sandbox, timeout=60)
    return out if rc == 0 else f"git diff failed: {err}"


def changed_files(sandbox: Path, base: str = "main", head: str = "HEAD") -> list[str]:
    rc, out, _ = _run(["git", "diff", "--name-only", f"{base}..{head}"], sandbox)
    return [l for l in out.splitlines() if l.strip()]


def current_branch(sandbox: Path) -> str:
    _, out, _ = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], sandbox)
    return out.strip()
