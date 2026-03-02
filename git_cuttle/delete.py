import subprocess
from dataclasses import replace
from pathlib import Path
from typing import Literal

from git_cuttle.errors import AppError
from git_cuttle.git_ops import add_worktree
from git_cuttle.git_ops import canonical_git_dir, repo_root
from git_cuttle.metadata_manager import MetadataManager, WorkspacesMetadata
from git_cuttle.plan_output import (
    DryRunPlan,
    PlanAction,
    render_human_plan,
    render_json_plan,
)
from git_cuttle.transaction import Transaction, TransactionStep
from git_cuttle.workspace_transaction import (
    backup_refs_step,
    cleanup_backup_refs_post_commit,
    rollback_restore_branch,
    run_command_transaction,
)

DeleteBlockReason = Literal[
    "current-workspace",
    "workspace-dirty",
    "no-upstream",
    "ahead-of-upstream",
]


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


def delete_block_reason(
    *, current: str | None, target: str, force: bool
) -> DeleteBlockReason | None:
    if current == target:
        return "current-workspace"
    if force:
        return None
    return None


def delete_workspace(
    *,
    cwd: Path,
    branch: str,
    metadata_manager: MetadataManager,
    force: bool = False,
    dry_run: bool = False,
    json_output: bool = False,
) -> str | None:
    repo_git_dir = canonical_git_dir(cwd)
    repo_root_dir = repo_root(cwd)
    if repo_git_dir is None or repo_root_dir is None:
        raise AppError(
            code="not-in-git-repo",
            message="gitcuttle must be run from within a git repository",
        )

    metadata = metadata_manager.read()
    repo_key = str(repo_git_dir)
    repo = metadata.repos.get(repo_key)
    if repo is None:
        raise AppError(
            code="repo-not-tracked",
            message="repository metadata is missing",
            guidance=("rerun the command to retry auto-tracking",),
        )

    workspace = repo.workspaces.get(branch)
    if workspace is None:
        raise AppError(
            code="workspace-not-tracked",
            message="workspace is not tracked",
            details=branch,
            guidance=(
                "run `git branch --list` to inspect local branches",
                "if needed, delete manually with `git branch -D <branch>` and `git worktree remove <path>`",
            ),
        )

    current = current_branch(cwd=cwd)
    block_reason = delete_block_reason(current=current, target=branch, force=force)
    if block_reason == "current-workspace":
        raise AppError(
            code="delete-blocked",
            message="cannot delete the current workspace",
            details=branch,
            guidance=("switch to a different branch and rerun",),
        )

    if (
        not force
        and workspace.worktree_path.exists()
        and _worktree_has_uncommitted_changes(cwd=workspace.worktree_path)
    ):
        raise AppError(
            code="workspace-dirty",
            message="workspace has uncommitted changes",
            details=str(workspace.worktree_path),
            guidance=("commit/stash changes or rerun with --force",),
        )

    if not force:
        upstream_ref = _workspace_upstream_ref(
            tracked_remote=workspace.tracked_remote,
            default_remote=repo.default_remote,
            branch=workspace.branch,
        )
        if upstream_ref is None or not _ref_exists(
            repo_root=repo_root_dir, ref=f"refs/remotes/{upstream_ref}"
        ):
            raise AppError(
                code="no-upstream",
                message="workspace has no upstream branch configured",
                details=workspace.branch,
                guidance=(
                    "set an upstream or rerun with --force",
                    f"example: git push -u origin {workspace.branch}",
                ),
            )

        ahead = _ahead_count(
            repo_root=repo_root_dir,
            local_branch=workspace.branch,
            upstream_ref=upstream_ref,
        )
        if ahead is None:
            raise AppError(
                code="no-upstream",
                message="workspace has no upstream branch configured",
                details=workspace.branch,
                guidance=(
                    "set an upstream or rerun with --force",
                    f"example: git push -u origin {workspace.branch}",
                ),
            )
        if ahead > 0:
            raise AppError(
                code="workspace-ahead",
                message="workspace branch is ahead of upstream",
                details=f"{workspace.branch} is ahead by {ahead} commit(s)",
                guidance=("push commits or rerun with --force",),
            )

    plan = _build_delete_plan(
        branch=branch, force=force, worktree_path=workspace.worktree_path
    )
    if dry_run:
        return render_json_plan(plan) if json_output else render_human_plan(plan)

    updated_workspaces = dict(repo.workspaces)
    updated_workspaces.pop(branch)
    updated_repo = replace(repo, workspaces=updated_workspaces)
    updated_repos = dict(metadata.repos)
    updated_repos[repo_key] = updated_repo
    updated_metadata = WorkspacesMetadata(version=metadata.version, repos=updated_repos)

    transaction = Transaction()
    transaction.add_step(
        backup_refs_step(
            repo_root=repo_root_dir,
            transaction=transaction,
            branches=(branch,),
            backup_error_code="delete-backup-failed",
            backup_error_message="failed to create transactional backup refs for delete",
            rollback_error_code="delete-rollback-failed",
            rollback_error_message="failed to rollback backup refs during delete",
        )
    )
    if workspace.worktree_path.exists():
        transaction.add_step(
            TransactionStep(
                name=f"remove-worktree:{branch}",
                apply=lambda: _remove_worktree(
                    repo_root=repo_root_dir,
                    worktree_path=workspace.worktree_path,
                    force=force,
                ),
                rollback=lambda: _restore_worktree(
                    repo_root=repo_root_dir,
                    branch=branch,
                    worktree_path=workspace.worktree_path,
                ),
                recovery_commands=(
                    f"git worktree add {workspace.worktree_path} {branch}",
                ),
            )
        )
    transaction.add_step(
        TransactionStep(
            name=f"delete-branch:{branch}",
            apply=lambda: _delete_local_branch(
                repo_root=repo_root_dir,
                branch=branch,
                force=force,
            ),
            rollback=lambda: rollback_restore_branch(
                repo_root=repo_root_dir,
                transaction=transaction,
                branch=branch,
                error_code="delete-rollback-failed",
                message="failed to restore deleted branch from backup ref",
            ),
        )
    )
    transaction.add_step(
        TransactionStep(
            name="write-metadata",
            apply=lambda: metadata_manager.write(updated_metadata),
            rollback=lambda: metadata_manager.write(metadata),
        )
    )
    run_command_transaction(
        transaction=transaction,
        code="delete-workspace-failed",
        message="failed to delete workspace",
    )
    cleanup_backup_refs_post_commit(
        repo_root=repo_root_dir,
        transaction=transaction,
        branches=(branch,),
        cleanup_error_code="delete-cleanup-failed",
        cleanup_error_message="failed to cleanup transactional backup refs for delete",
    )
    return None


def _build_delete_plan(*, branch: str, force: bool, worktree_path: Path) -> DryRunPlan:
    actions = [PlanAction(op="delete-worktree", target=str(worktree_path))]
    actions.append(
        PlanAction(
            op="delete-branch",
            target=branch,
            details="forced" if force else None,
        )
    )
    actions.append(PlanAction(op="untrack-workspace", target=branch))
    return DryRunPlan(command="delete", actions=tuple(actions))


def _workspace_upstream_ref(
    *, tracked_remote: str | None, default_remote: str | None, branch: str
) -> str | None:
    remote_name = tracked_remote or default_remote
    if remote_name is None:
        return None
    return f"{remote_name}/{branch}"


def _ref_exists(*, repo_root: Path, ref: str) -> bool:
    result = subprocess.run(
        ["git", "rev-parse", "--verify", ref],
        capture_output=True,
        text=True,
        check=False,
        cwd=repo_root,
    )
    return result.returncode == 0


def _ahead_count(
    *, repo_root: Path, local_branch: str, upstream_ref: str
) -> int | None:
    result = subprocess.run(
        [
            "git",
            "rev-list",
            "--left-right",
            "--count",
            f"{local_branch}...{upstream_ref}",
        ],
        capture_output=True,
        text=True,
        check=False,
        cwd=repo_root,
    )
    if result.returncode != 0:
        return None

    parts = result.stdout.strip().split()
    if len(parts) != 2:
        return None

    try:
        return int(parts[0])
    except ValueError:
        return None


def _worktree_has_uncommitted_changes(*, cwd: Path) -> bool:
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        capture_output=True,
        text=True,
        check=False,
        cwd=cwd,
    )
    return result.returncode == 0 and bool(result.stdout.strip())


def _remove_worktree(*, repo_root: Path, worktree_path: Path, force: bool) -> None:
    args = ["git", "worktree", "remove"]
    if force:
        args.append("--force")
    args.append(str(worktree_path))

    result = subprocess.run(
        args,
        capture_output=True,
        text=True,
        check=False,
        cwd=repo_root,
    )
    if result.returncode != 0:
        raise AppError(
            code="worktree-delete-failed",
            message="failed to delete workspace worktree",
            details=result.stderr.strip() or str(worktree_path),
        )


def _delete_local_branch(*, repo_root: Path, branch: str, force: bool) -> None:
    delete_flag = "-D" if force else "-d"
    result = subprocess.run(
        ["git", "branch", delete_flag, branch],
        capture_output=True,
        text=True,
        check=False,
        cwd=repo_root,
    )
    if result.returncode != 0:
        raise AppError(
            code="branch-delete-failed",
            message="failed to delete workspace branch",
            details=result.stderr.strip() or branch,
        )


def _restore_worktree(*, repo_root: Path, branch: str, worktree_path: Path) -> None:
    if worktree_path.exists():
        return
    try:
        add_worktree(branch=branch, path=worktree_path, cwd=repo_root)
    except RuntimeError as error:
        raise AppError(
            code="delete-rollback-failed",
            message="failed to restore workspace worktree during rollback",
            details=str(error),
        ) from error
