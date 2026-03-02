from pathlib import Path
import subprocess


def current_branch(*, cwd: Path) -> str | None:
    result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
        cwd=cwd,
    )
    if result.returncode != 0:
        return None

    branch = result.stdout.strip()
    if branch == "" or branch == "HEAD":
        return None
    return branch


def delete_block_reason(*, current: str | None, target: str, force: bool) -> str | None:
    if force:
        return None
    if current == target:
        return "current-workspace"
    return None
