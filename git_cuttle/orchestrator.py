import json
import subprocess
from pathlib import Path
from typing import Callable, Protocol

from git_cuttle.absorb import absorb_octopus_workspace
from git_cuttle.delete import delete_workspace
from git_cuttle.errors import AppError
from git_cuttle.git_ops import (
    canonical_git_dir,
    in_git_repo,
    in_progress_operation,
    repo_root,
)
from git_cuttle.lib import Options
from git_cuttle.list_output import render_workspace_table, rows_for_repo
from git_cuttle.metadata_manager import MetadataManager, RepoMetadata, WorkspaceMetadata
from git_cuttle.new import (
    create_octopus_workspace,
    create_standard_workspace,
    resolve_workspace_branch_name,
)
from git_cuttle.prune import PrStatus, prune_workspaces
from git_cuttle.remote_status import (
    PullRequestStatusCache,
    RemoteStatusCache,
    pull_request_status_for_repo,
    remote_ahead_behind_for_repo,
)
from git_cuttle.update import update_non_octopus_workspace, update_octopus_workspace

MUTATING_COMMANDS = frozenset({"new", "delete", "prune", "update", "absorb"})
REMOTE_STATUS_CACHE = RemoteStatusCache()
PULL_REQUEST_STATUS_CACHE = PullRequestStatusCache()


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
        manager = (
            metadata_manager
            if isinstance(metadata_manager, MetadataManager)
            else MetadataManager()
        )
        _run_new(opts=opts, cwd=cwd, metadata_manager=manager)
        return
    if command_name == "list":
        manager = (
            metadata_manager
            if isinstance(metadata_manager, MetadataManager)
            else MetadataManager()
        )
        _run_list(opts=opts, cwd=cwd, metadata_manager=manager)
        return
    if command_name == "delete":
        manager = (
            metadata_manager
            if isinstance(metadata_manager, MetadataManager)
            else MetadataManager()
        )
        _run_delete(opts=opts, cwd=cwd, metadata_manager=manager)
        return
    if command_name == "prune":
        manager = (
            metadata_manager
            if isinstance(metadata_manager, MetadataManager)
            else MetadataManager()
        )
        _run_prune(opts=opts, cwd=cwd, metadata_manager=manager)
        return
    if command_name == "update":
        manager = (
            metadata_manager
            if isinstance(metadata_manager, MetadataManager)
            else MetadataManager()
        )
        _run_update(opts=opts, cwd=cwd, metadata_manager=manager)
        return
    if command_name == "absorb":
        manager = (
            metadata_manager
            if isinstance(metadata_manager, MetadataManager)
            else MetadataManager()
        )
        _run_absorb(opts=opts, cwd=cwd, metadata_manager=manager)
        return

    raise AppError(
        code="unknown-command",
        message="unknown command requested",
        details=command_name,
        guidance=("run `gitcuttle --help` to view available commands",),
    )


def _run_new(*, opts: Options, cwd: Path, metadata_manager: MetadataManager) -> None:
    repo = _tracked_repo_for_cwd(cwd=cwd, metadata_manager=metadata_manager)
    branch = resolve_workspace_branch_name(
        cwd=repo.repo_root,
        requested_branch=opts.branch,
        remote=repo.default_remote,
    )

    if opts.parent_refs:
        destination = create_octopus_workspace(
            cwd=cwd,
            branch=branch,
            parent_refs=list(opts.parent_refs),
            metadata_manager=metadata_manager,
        )
    else:
        destination = create_standard_workspace(
            cwd=cwd,
            branch=branch,
            base_ref=opts.base_ref,
            metadata_manager=metadata_manager,
        )

    if opts.destination:
        print(destination)
        return

    print(f"created workspace '{branch}' at {destination}")
    print(f"hint: cd {destination}")


def _run_list(*, opts: Options, cwd: Path, metadata_manager: MetadataManager) -> None:
    tracked_repo = _tracked_repo_for_list(cwd=cwd, metadata_manager=metadata_manager)

    if tracked_repo is None:
        if opts.json_output:
            print('{"workspaces":[]}')
            return
        print(render_workspace_table([]))
        return

    remote_statuses = REMOTE_STATUS_CACHE.statuses_for_repo(
        repo=tracked_repo,
        resolver=lambda repo: remote_ahead_behind_for_repo(repo=repo),
    )
    pr_statuses = PULL_REQUEST_STATUS_CACHE.statuses_for_repo(
        repo=tracked_repo,
        resolver=lambda repo: pull_request_status_for_repo(repo=repo),
    )

    rows = rows_for_repo(
        repo=tracked_repo,
        remote_statuses=remote_statuses,
        pr_statuses=pr_statuses,
    )

    if opts.json_output:
        payload = {
            "workspaces": [
                {
                    "repo": row.repo,
                    "branch": row.branch,
                    "dirty": row.dirty,
                    "ahead": row.ahead,
                    "behind": row.behind,
                    "pr": row.pull_request,
                    "description": row.description,
                    "worktree": row.worktree_path,
                }
                for row in rows
            ]
        }
        print(json.dumps(payload))
        return

    print(render_workspace_table(rows))


def _tracked_repo_for_list(
    *, cwd: Path, metadata_manager: MetadataManager
) -> RepoMetadata | None:
    repo_git_dir = canonical_git_dir(cwd)
    if repo_git_dir is None:
        return None

    metadata = metadata_manager.read()
    return metadata.repos.get(str(repo_git_dir))


def _run_delete(*, opts: Options, cwd: Path, metadata_manager: MetadataManager) -> None:
    if opts.branch is None:
        raise AppError(
            code="invalid-arguments",
            message="delete command requires a branch name",
            guidance=("pass `gitcuttle delete <branch>`",),
        )

    rendered = delete_workspace(
        cwd=cwd,
        branch=opts.branch,
        metadata_manager=metadata_manager,
        force=opts.force,
        dry_run=opts.dry_run,
        json_output=opts.json_output,
    )
    if rendered is not None:
        print(rendered)


def _run_prune(*, opts: Options, cwd: Path, metadata_manager: MetadataManager) -> None:
    tracked_repo = _tracked_repo_for_cwd(cwd=cwd, metadata_manager=metadata_manager)
    pull_request_statuses = PULL_REQUEST_STATUS_CACHE.statuses_for_repo(
        repo=tracked_repo,
        resolver=lambda repo: pull_request_status_for_repo(repo=repo),
    )

    pr_status_by_branch: dict[str, PrStatus | None] = {}
    for branch, status in pull_request_statuses.items():
        state: PrStatus | None
        if status.state == "draft":
            state = "open"
        elif status.state in {"open", "closed", "merged", "unknown", "unavailable"}:
            state = status.state
        else:
            state = None
        pr_status_by_branch[branch] = state

    rendered = prune_workspaces(
        cwd=cwd,
        metadata_manager=metadata_manager,
        pr_status_by_branch=pr_status_by_branch,
        force=opts.force,
        dry_run=opts.dry_run,
        json_output=opts.json_output,
    )
    if rendered is not None:
        print(rendered)


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
    print(
        f"updated standard workspace {standard_result.branch} onto {standard_result.upstream_ref}"
    )


def _tracked_repo_for_cwd(
    *, cwd: Path, metadata_manager: MetadataManager
) -> RepoMetadata:
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


def _git_stdout(*, repo_root: Path, args: list[str], code: str, message: str) -> str:
    result = subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        check=False,
        cwd=repo_root,
    )
    if result.returncode != 0:
        details = result.stderr.strip() or result.stdout.strip() or " ".join(args)
        raise AppError(code=code, message=message, details=details)
    return result.stdout.strip()


def _run_absorb(*, opts: Options, cwd: Path, metadata_manager: MetadataManager) -> None:
    if opts.target_parent is not None and opts.interactive:
        raise AppError(
            code="invalid-absorb-options",
            message="cannot combine an explicit target parent with interactive mode",
            guidance=(
                "use either `gitcuttle absorb <parent>` or `gitcuttle absorb -i`",
            ),
        )

    repo = _tracked_repo_for_cwd(cwd=cwd, metadata_manager=metadata_manager)
    workspace = _current_workspace(cwd=cwd, repo=repo)

    chooser = (
        _interactive_target_selector(repo_root=repo.repo_root)
        if opts.interactive
        else None
    )
    result = absorb_octopus_workspace(
        repo_root=repo.repo_root,
        workspace=workspace,
        target_parent=opts.target_parent,
        interactive=opts.interactive,
        choose_target=chooser,
    )

    if not result.absorbed_commits:
        print(f"no post-merge commits to absorb for {result.branch}")
        return

    print(f"absorbed {len(result.absorbed_commits)} commit(s) from {result.branch}")


def _interactive_target_selector(
    *, repo_root: Path
) -> Callable[[str, tuple[str, ...]], str]:
    def choose_target(commit: str, parents: tuple[str, ...]) -> str:
        subject = _git_stdout(
            repo_root=repo_root,
            args=["show", "-s", "--format=%s", commit],
            code="absorb-interactive-inspect-failed",
            message="failed to read commit details during interactive absorb",
        )
        short_oid = commit[:12]
        print(f"choose parent branch for {short_oid}: {subject}")
        for index, parent in enumerate(parents, start=1):
            print(f"  {index}) {parent}")

        try:
            selection = input("target parent> ").strip()
        except EOFError as exc:
            raise AppError(
                code="interactive-selection-failed",
                message="interactive absorb selection was interrupted",
                guidance=(
                    "rerun with `-i` and provide a selection or pass an explicit parent",
                ),
            ) from exc

        selected_parent: str | None = None
        if selection.isdigit():
            selected_index = int(selection)
            if 1 <= selected_index <= len(parents):
                selected_parent = parents[selected_index - 1]
        elif selection in parents:
            selected_parent = selection

        if selected_parent is None:
            raise AppError(
                code="invalid-absorb-target",
                message="interactive absorb target is not a valid octopus parent",
                details=selection or "<empty>",
                guidance=(
                    "rerun with `-i` and select one of the listed parent branches",
                    "or rerun with an explicit target parent",
                ),
            )

        return selected_parent

    return choose_target
