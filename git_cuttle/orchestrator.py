from pathlib import Path

from git_cuttle.errors import AppError
from git_cuttle.git_ops import in_git_repo
from git_cuttle.lib import Options, greet
from git_cuttle.metadata_manager import MetadataManager


def run(
    opts: Options,
    *,
    cwd: Path | None = None,
    metadata_manager: MetadataManager | None = None,
) -> None:
    effective_cwd = cwd or Path.cwd()
    if not in_git_repo(effective_cwd):
        raise AppError(
            code="not-in-git-repo",
            message="gitcuttle must be run from within a git repository",
            guidance=(
                "change to your repository root or one of its worktrees and retry",
            ),
        )

    _ = metadata_manager or MetadataManager()
    if opts.destination:
        print(effective_cwd.resolve())
        return

    greet(opts)
