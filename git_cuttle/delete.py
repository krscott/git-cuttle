from dataclasses import replace
from pathlib import Path
import subprocess

from git_cuttle.errors import AppError
from git_cuttle.git_ops import canonical_git_dir, repo_root
from git_cuttle.metadata_manager import MetadataManager, WorkspacesMetadata
from git_cuttle.plan_output import DryRunPlan, PlanAction, render_human_plan, render_json_plan


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
            guidance=("run `gitcuttle list` to inspect tracked workspaces",),
        )

    block_reason = delete_block_reason(
        current=current_branch(cwd=cwd),
        target=branch,
        force=force,
    )
    if block_reason is not None:
        raise AppError(
            code="delete-blocked",
            message="cannot delete the current workspace",
            details=branch,
            guidance=("switch to a different branch or rerun with --force",),
        )

    if not force and workspace.worktree_path.exists() and _worktree_has_uncommitted_changes(cwd=workspace.worktree_path):
        raise AppError(
            code="workspace-dirty",
            message="workspace has uncommitted changes",
            details=str(workspace.worktree_path),
            guidance=("commit/stash changes or rerun with --force",),
        )

    plan = _build_delete_plan(branch=branch, force=force, worktree_path=workspace.worktree_path)
    if dry_run:
        return render_json_plan(plan) if json_output else render_human_plan(plan)

    if workspace.worktree_path.exists():
        _remove_worktree(
            repo_root=repo_root_dir,
            worktree_path=workspace.worktree_path,
            force=force,
        )
    _delete_local_branch(repo_root=repo_root_dir, branch=branch, force=force)

    updated_workspaces = dict(repo.workspaces)
    updated_workspaces.pop(branch)
    updated_repo = replace(repo, workspaces=updated_workspaces)
    updated_repos = dict(metadata.repos)
    updated_repos[repo_key] = updated_repo
    metadata_manager.write(WorkspacesMetadata(version=metadata.version, repos=updated_repos))
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
