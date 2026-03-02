import subprocess
from pathlib import Path


def in_git_repo(cwd: Path | None = None) -> bool:
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=False,
        cwd=cwd,
    )
    return result.returncode == 0
