import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)


@dataclass(kw_only=True, frozen=True)
class Options:
    name: str


def in_git_repo(cwd: Path | None = None) -> bool:
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=False,
        cwd=cwd,
    )
    return result.returncode == 0


def greet(opts: Options) -> None:
    """Print a greeting message.

    Args:
        name: The name of the person to greet.
    """
    log.debug("Greeting user...")
    print(f"Hello, {opts.name}!")
