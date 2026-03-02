from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
import subprocess

from git_cuttle.errors import AppError
from git_cuttle.git_ops import canonical_git_dir, repo_root
from git_cuttle.metadata_manager import MetadataManager, WorkspaceMetadata, WorkspacesMetadata
from git_cuttle.workspace_paths import derive_workspace_path


def resolve_base_ref(*, cwd: Path, base_ref: str | None) -> str:
    if base_ref is not None:
        if _rev_parse(cwd=cwd, ref=base_ref) is None:
            raise AppError(
                code="invalid-base-ref",
                message="base ref does not exist",
                details=base_ref,
                guidance=("pass a valid local branch, tag, or commit",),
            )
        return base_ref

    current_branch_name = _current_branch(cwd=cwd)
    if current_branch_name is None:
        raise AppError(
            code="detached-head",
            message="cannot infer base ref while HEAD is detached",
            guidance=("pass --base <ref> explicitly",),
        )
    return current_branch_name


def create_standard_workspace(
    *,
    cwd: Path,
    branch: str,
    base_ref: str | None,
    metadata_manager: MetadataManager,
) -> Path:
    metadata_manager.ensure_repo_tracked(cwd=cwd)

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

    if _local_branch_exists(cwd=repo_root_dir, branch=branch):
        raise AppError(
            code="branch-already-exists",
            message="target branch already exists",
            details=branch,
            guidance=("choose a new branch name",),
        )

    resolved_base_ref = resolve_base_ref(cwd=repo_root_dir, base_ref=base_ref)
    _create_branch(cwd=repo_root_dir, branch=branch, base_ref=resolved_base_ref)

    destination = derive_workspace_path(
        git_dir=repo_git_dir,
        branch=branch,
        sibling_branches=repo.workspaces.keys(),
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    _add_worktree(cwd=repo_root_dir, branch=branch, destination=destination)

    timestamp = _utc_now_iso()
    updated_workspaces = dict(repo.workspaces)
    updated_workspaces[branch] = WorkspaceMetadata(
        branch=branch,
        worktree_path=destination,
        tracked_remote=repo.default_remote,
        kind="standard",
        base_ref=resolved_base_ref,
        octopus_parents=(),
        created_at=timestamp,
        updated_at=timestamp,
    )

    repos = dict(metadata.repos)
    repos[repo_key] = replace(repo, updated_at=timestamp, workspaces=updated_workspaces)
    metadata_manager.write(WorkspacesMetadata(version=metadata.version, repos=repos))
    return destination


def create_octopus_workspace(
    *,
    cwd: Path,
    branch: str,
    parent_refs: list[str],
    metadata_manager: MetadataManager,
) -> Path:
    metadata_manager.ensure_repo_tracked(cwd=cwd)

    repo_git_dir = canonical_git_dir(cwd)
    repo_root_dir = repo_root(cwd)
    if repo_git_dir is None or repo_root_dir is None:
        raise AppError(
            code="not-in-git-repo",
            message="gitcuttle must be run from within a git repository",
        )

    normalized_parent_refs = _normalize_octopus_parent_refs(
        cwd=repo_root_dir,
        parent_refs=parent_refs,
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

    if _local_branch_exists(cwd=repo_root_dir, branch=branch):
        raise AppError(
            code="branch-already-exists",
            message="target branch already exists",
            details=branch,
            guidance=("choose a new branch name",),
        )

    _create_branch(cwd=repo_root_dir, branch=branch, base_ref=normalized_parent_refs[0])

    destination = derive_workspace_path(
        git_dir=repo_git_dir,
        branch=branch,
        sibling_branches=repo.workspaces.keys(),
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    _add_worktree(cwd=repo_root_dir, branch=branch, destination=destination)
    _create_octopus_merge_commit(
        cwd=destination,
        branch=branch,
        merge_parents=normalized_parent_refs[1:],
    )

    timestamp = _utc_now_iso()
    updated_workspaces = dict(repo.workspaces)
    updated_workspaces[branch] = WorkspaceMetadata(
        branch=branch,
        worktree_path=destination,
        tracked_remote=repo.default_remote,
        kind="octopus",
        base_ref=normalized_parent_refs[0],
        octopus_parents=tuple(normalized_parent_refs),
        created_at=timestamp,
        updated_at=timestamp,
    )

    repos = dict(metadata.repos)
    repos[repo_key] = replace(repo, updated_at=timestamp, workspaces=updated_workspaces)
    metadata_manager.write(WorkspacesMetadata(version=metadata.version, repos=repos))
    return destination


def _utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z")


def _current_branch(*, cwd: Path) -> str | None:
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


def _rev_parse(*, cwd: Path, ref: str) -> str | None:
    result = subprocess.run(
        ["git", "rev-parse", "--verify", ref],
        capture_output=True,
        text=True,
        check=False,
        cwd=cwd,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def _local_branch_exists(*, cwd: Path, branch: str) -> bool:
    result = subprocess.run(
        ["git", "show-ref", "--verify", "--quiet", f"refs/heads/{branch}"],
        capture_output=True,
        text=True,
        check=False,
        cwd=cwd,
    )
    return result.returncode == 0


def _create_branch(*, cwd: Path, branch: str, base_ref: str) -> None:
    result = subprocess.run(
        ["git", "branch", branch, base_ref],
        capture_output=True,
        text=True,
        check=False,
        cwd=cwd,
    )
    if result.returncode != 0:
        raise AppError(
            code="branch-create-failed",
            message="failed to create branch",
            details=result.stderr.strip() or f"{branch} from {base_ref}",
        )


def _add_worktree(*, cwd: Path, branch: str, destination: Path) -> None:
    result = subprocess.run(
        ["git", "worktree", "add", str(destination), branch],
        capture_output=True,
        text=True,
        check=False,
        cwd=cwd,
    )
    if result.returncode != 0:
        raise AppError(
            code="worktree-create-failed",
            message="failed to create worktree",
            details=result.stderr.strip() or str(destination),
        )


def _create_octopus_merge_commit(*, cwd: Path, branch: str, merge_parents: list[str]) -> None:
    result = subprocess.run(
        [
            "git",
            "merge",
            "--no-ff",
            "-m",
            f"Create octopus workspace {branch}",
            *merge_parents,
        ],
        capture_output=True,
        text=True,
        check=False,
        cwd=cwd,
    )
    if result.returncode != 0:
        raise AppError(
            code="octopus-merge-failed",
            message="failed to create octopus merge commit",
            details=result.stderr.strip() or result.stdout.strip() or branch,
            guidance=(
                "resolve parent branch conflicts before retrying octopus workspace creation",
            ),
        )


def _normalize_octopus_parent_refs(*, cwd: Path, parent_refs: list[str]) -> list[str]:
    normalized = [ref.strip() for ref in parent_refs if ref.strip()]
    if len(normalized) < 2:
        raise AppError(
            code="invalid-octopus-parents",
            message="octopus workspace requires at least two parent refs",
            guidance=("pass at least two branch names, tags, or commit refs",),
        )

    if len(set(normalized)) != len(normalized):
        raise AppError(
            code="invalid-octopus-parents",
            message="octopus parent refs must be unique",
            details=", ".join(normalized),
        )

    missing_refs = [ref for ref in normalized if _rev_parse(cwd=cwd, ref=ref) is None]
    if missing_refs:
        raise AppError(
            code="invalid-base-ref",
            message="one or more octopus parent refs do not exist",
            details=", ".join(missing_refs),
            guidance=("pass valid local branches, tags, or commit refs",),
        )

    return normalized
