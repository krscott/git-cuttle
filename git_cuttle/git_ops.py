import subprocess
from pathlib import Path


IN_PROGRESS_STATE_MARKERS = (
    "MERGE_HEAD",
    "CHERRY_PICK_HEAD",
    "REVERT_HEAD",
    "REBASE_HEAD",
    "rebase-apply",
    "rebase-merge",
)


def in_git_repo(cwd: Path | None = None) -> bool:
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=False,
        cwd=cwd,
    )
    return result.returncode == 0


def git_dir(cwd: Path | None = None) -> Path | None:
    result = subprocess.run(
        ["git", "rev-parse", "--git-dir"],
        capture_output=True,
        text=True,
        check=False,
        cwd=cwd,
    )
    if result.returncode != 0:
        return None

    candidate = Path(result.stdout.strip())
    if candidate.is_absolute():
        return candidate

    base_dir = cwd or Path.cwd()
    return (base_dir / candidate).resolve(strict=False)


def in_progress_operation(cwd: Path | None = None) -> str | None:
    repo_git_dir = git_dir(cwd)
    if repo_git_dir is None:
        return None

    for marker in IN_PROGRESS_STATE_MARKERS:
        if (repo_git_dir / marker).exists():
            return marker

    return None
