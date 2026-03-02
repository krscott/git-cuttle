from pathlib import Path
import subprocess
from typing import Protocol

from git_cuttle.errors import AppError
from git_cuttle.git_ops import canonical_git_dir, in_git_repo, in_progress_operation, repo_root
from git_cuttle.lib import Options
from git_cuttle.metadata_manager import MetadataManager, RepoMetadata, WorkspaceMetadata
from git_cuttle.update import update_non_octopus_workspace, update_octopus_workspace


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

    _dispatch_command(
        command_name=command_name,
        opts=opts,
        cwd=effective_cwd,
        metadata_manager=tracker,
    )


def _dispatch_command(
    *,
    command_name: str,
    opts: Options,
    cwd: Path,
    metadata_manager: RepoTracker,
) -> None:
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
        manager = metadata_manager if isinstance(metadata_manager, MetadataManager) else MetadataManager()
        _run_update(opts=opts, cwd=cwd, metadata_manager=manager)
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


def _run_update(*, opts: Options, cwd: Path, metadata_manager: MetadataManager) -> None:
    _ = opts
    repo = _tracked_repo_for_cwd(cwd=cwd, metadata_manager=metadata_manager)
    workspace = _current_workspace(cwd=cwd, repo=repo)

    if workspace.kind == "octopus":
        octopus_result = update_octopus_workspace(
            repo_root=repo.repo_root,
            workspace=workspace,
            default_remote=repo.default_remote,
        )
        print(
            f"rebuilt octopus workspace {octopus_result.branch} from {', '.join(octopus_result.parent_refs)}; "
            f"replayed {len(octopus_result.replayed_commits)} commit(s)"
        )
        return

    standard_result = update_non_octopus_workspace(
        repo_root=repo.repo_root,
        workspace=workspace,
        default_remote=repo.default_remote,
    )
    print(f"updated standard workspace {standard_result.branch} onto {standard_result.upstream_ref}")


def _tracked_repo_for_cwd(*, cwd: Path, metadata_manager: MetadataManager) -> RepoMetadata:
    repo_git_dir = canonical_git_dir(cwd)
    if repo_git_dir is None:
        raise AppError(
            code="not-in-git-repo",
            message="gitcuttle must be run from within a git repository",
        )

    metadata = metadata_manager.read()
    repo = metadata.repos.get(str(repo_git_dir))
    if repo is None:
        raise AppError(
            code="repo-not-tracked",
            message="repository metadata is missing",
            guidance=("rerun the command to retry auto-tracking",),
        )
    return repo


def _current_workspace(*, cwd: Path, repo: RepoMetadata) -> WorkspaceMetadata:
    branch = _current_branch(cwd=cwd)
    if branch is None:
        raise AppError(
            code="detached-head",
            message="cannot update from a detached HEAD state",
            guidance=("checkout a branch and retry",),
        )

    workspace = repo.workspaces.get(branch)
    if workspace is None:
        raise AppError(
            code="workspace-not-tracked",
            message="current branch is not a tracked workspace",
            details=branch,
            guidance=("run `gitcuttle list` to inspect tracked workspaces",),
        )
    return workspace


def _current_branch(*, cwd: Path) -> str | None:
    root = repo_root(cwd)
    if root is None:
        return None

    result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
        cwd=root,
    )
    if result.returncode != 0:
        return None

    branch = result.stdout.strip()
    if branch == "" or branch == "HEAD":
        return None
    return branch


def _run_absorb(*, opts: Options) -> None:
    _ = opts
    print("absorb:invoked")
