from pathlib import Path
from typing import Protocol

from git_cuttle.errors import AppError
from git_cuttle.git_ops import in_git_repo, in_progress_operation
from git_cuttle.lib import Options
from git_cuttle.metadata_manager import MetadataManager


MUTATING_COMMANDS = frozenset({"new", "delete", "prune", "update", "absorb"})


class RepoTracker(Protocol):
    def ensure_repo_tracked(self, *, cwd: Path) -> None: ...


def command_requires_auto_tracking(command_name: str) -> bool:
    return command_name in MUTATING_COMMANDS


def run(
    opts: Options,
    *,
    cwd: Path | None = None,
    metadata_manager: RepoTracker | None = None,
    command_name: str = "list",
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

    in_progress_marker = in_progress_operation(effective_cwd)
    if in_progress_marker is not None:
        raise AppError(
            code="git-operation-in-progress",
            message="repository has an in-progress git operation",
            details=f"detected state marker: {in_progress_marker}",
            guidance=(
                "resolve or abort the git operation and rerun gitcuttle",
                "examples: git merge --abort, git rebase --abort, git cherry-pick --abort",
            ),
        )

    tracker = metadata_manager or MetadataManager()
    if command_requires_auto_tracking(command_name):
        tracker.ensure_repo_tracked(cwd=effective_cwd)

    _dispatch_command(command_name=command_name, opts=opts)


def _dispatch_command(*, command_name: str, opts: Options) -> None:
    if command_name == "new":
        _run_new(opts=opts)
        return
    if command_name == "list":
        _run_list(opts=opts)
        return
    if command_name == "delete":
        _run_delete(opts=opts)
        return
    if command_name == "prune":
        _run_prune(opts=opts)
        return
    if command_name == "update":
        _run_update(opts=opts)
        return
    if command_name == "absorb":
        _run_absorb(opts=opts)
        return

    raise AppError(
        code="unknown-command",
        message="unknown command requested",
        details=command_name,
        guidance=("run `gitcuttle --help` to view available commands",),
    )


def _run_new(*, opts: Options) -> None:
    if opts.destination:
        print("new:destination")
        return
    print("new:invoked")


def _run_list(*, opts: Options) -> None:
    if opts.json_output:
        print('{"command":"list","status":"invoked"}')
        return
    print("list:invoked")


def _run_delete(*, opts: Options) -> None:
    if opts.dry_run:
        if opts.json_output:
            print('{"command":"delete","status":"planned"}')
            return
        print("delete:planned")
        return
    print("delete:invoked")


def _run_prune(*, opts: Options) -> None:
    if opts.dry_run:
        if opts.json_output:
            print('{"command":"prune","status":"planned"}')
            return
        print("prune:planned")
        return
    print("prune:invoked")


def _run_update(*, opts: Options) -> None:
    _ = opts
    print("update:invoked")


def _run_absorb(*, opts: Options) -> None:
    _ = opts
    print("absorb:invoked")
