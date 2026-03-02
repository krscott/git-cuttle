import subprocess
import secrets
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from git_cuttle.errors import AppError
from git_cuttle.git_ops import canonical_git_dir, repo_root
from git_cuttle.metadata_manager import (
    MetadataManager,
    WorkspaceMetadata,
    WorkspacesMetadata,
)
from git_cuttle.transaction import Transaction, TransactionStep
from git_cuttle.workspace_paths import derive_workspace_path
from git_cuttle.workspace_transaction import run_command_transaction

_HEX_TO_INVERSE_ALPHA = str.maketrans("0123456789abcdef", "zyxwvutsrqponmlk")


def resolve_base_ref(*, cwd: Path, base_ref: str | None) -> str:
    if base_ref is not None:
        if _rev_parse(cwd=cwd, ref=base_ref) is None:
            raise AppError(
                code="invalid-base-ref",
                message="base ref does not exist",
                details=base_ref,
                guidance=(
                    "pass a valid local branch, tag, or commit",
                    "or run `gitcuttle new -b <name>` to base from the current commit",
                ),
            )
        return base_ref

    current_commit = _rev_parse(cwd=cwd, ref="HEAD")
    if current_commit is None:
        raise AppError(
            code="base-resolve-failed",
            message="failed to resolve current commit for default base",
            guidance=("pass an explicit base ref as `gitcuttle new <base> -b <name>`",),
        )
    return current_commit


def resolve_workspace_branch_name(
    *, cwd: Path, requested_branch: str | None, remote: str | None
) -> str:
    if requested_branch is not None:
        return requested_branch

    for _ in range(32):
        candidate = _generate_workspace_branch_name()
        if not _branch_exists(cwd=cwd, branch=candidate, remote=remote):
            return candidate

    raise AppError(
        code="branch-name-generation-failed",
        message="failed to generate a unique workspace branch name",
        guidance=(
            "retry the command",
            "or pass an explicit name with `gitcuttle new -b <name>`",
        ),
    )


def _generate_workspace_branch_name() -> str:
    random_hex = secrets.token_hex(4)
    inverse_hex = random_hex.translate(_HEX_TO_INVERSE_ALPHA)
    return f"workspace-{inverse_hex}"


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

    if _branch_exists(
        cwd=repo_root_dir,
        branch=branch,
        remote=repo.default_remote,
    ):
        raise AppError(
            code="branch-already-exists",
            message="target branch already exists",
            details=branch,
            guidance=("choose a new branch name",),
        )

    resolved_base_ref = resolve_base_ref(cwd=repo_root_dir, base_ref=base_ref)
    destination = derive_workspace_path(
        git_dir=repo_git_dir,
        branch=branch,
        sibling_branches=repo.workspaces.keys(),
    )
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
    updated_metadata = WorkspacesMetadata(version=metadata.version, repos=repos)

    transaction = Transaction()
    transaction.add_step(
        TransactionStep(
            name=f"create-branch:{branch}",
            apply=lambda: _create_branch(
                cwd=repo_root_dir,
                branch=branch,
                base_ref=resolved_base_ref,
            ),
            rollback=lambda: _delete_branch_if_exists(cwd=repo_root_dir, branch=branch),
        )
    )
    transaction.add_step(
        TransactionStep(
            name=f"add-worktree:{branch}",
            apply=lambda: _prepare_and_add_worktree(
                cwd=repo_root_dir,
                branch=branch,
                destination=destination,
            ),
            rollback=lambda: _remove_worktree_if_exists(
                cwd=repo_root_dir,
                destination=destination,
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
        code="new-workspace-failed",
        message="failed to create workspace",
    )
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

    if _branch_exists(
        cwd=repo_root_dir,
        branch=branch,
        remote=repo.default_remote,
    ):
        raise AppError(
            code="branch-already-exists",
            message="target branch already exists",
            details=branch,
            guidance=("choose a new branch name",),
        )

    destination = derive_workspace_path(
        git_dir=repo_git_dir,
        branch=branch,
        sibling_branches=repo.workspaces.keys(),
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
    updated_metadata = WorkspacesMetadata(version=metadata.version, repos=repos)

    transaction = Transaction()
    transaction.add_step(
        TransactionStep(
            name=f"create-branch:{branch}",
            apply=lambda: _create_branch(
                cwd=repo_root_dir,
                branch=branch,
                base_ref=normalized_parent_refs[0],
            ),
            rollback=lambda: _delete_branch_if_exists(cwd=repo_root_dir, branch=branch),
        )
    )
    transaction.add_step(
        TransactionStep(
            name=f"add-worktree:{branch}",
            apply=lambda: _prepare_and_add_worktree(
                cwd=repo_root_dir,
                branch=branch,
                destination=destination,
            ),
            rollback=lambda: _remove_worktree_if_exists(
                cwd=repo_root_dir,
                destination=destination,
            ),
        )
    )
    transaction.add_step(
        TransactionStep(
            name=f"merge-octopus:{branch}",
            apply=lambda: _create_octopus_merge_commit(
                cwd=destination,
                branch=branch,
                merge_parents=normalized_parent_refs[1:],
            ),
            rollback=lambda: None,
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
        code="new-workspace-failed",
        message="failed to create workspace",
    )
    return destination


def _prepare_and_add_worktree(*, cwd: Path, branch: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    _add_worktree(cwd=cwd, branch=branch, destination=destination)


def _remove_worktree_if_exists(*, cwd: Path, destination: Path) -> None:
    if not destination.exists():
        return
    result = subprocess.run(
        ["git", "worktree", "remove", "--force", str(destination)],
        capture_output=True,
        text=True,
        check=False,
        cwd=cwd,
    )
    if result.returncode != 0:
        raise AppError(
            code="new-rollback-failed",
            message="failed to rollback workspace worktree",
            details=result.stderr.strip() or str(destination),
        )


def _delete_branch_if_exists(*, cwd: Path, branch: str) -> None:
    if not _local_branch_exists(cwd=cwd, branch=branch):
        return
    result = subprocess.run(
        ["git", "branch", "-D", branch],
        capture_output=True,
        text=True,
        check=False,
        cwd=cwd,
    )
    if result.returncode != 0:
        raise AppError(
            code="new-rollback-failed",
            message="failed to rollback workspace branch",
            details=result.stderr.strip() or branch,
        )


def _utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z")


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


def _remote_branch_exists(*, cwd: Path, branch: str, remote: str) -> bool:
    result = subprocess.run(
        ["git", "ls-remote", "--exit-code", "--heads", remote, f"refs/heads/{branch}"],
        capture_output=True,
        text=True,
        check=False,
        cwd=cwd,
    )
    if result.returncode == 0:
        return True
    if result.returncode == 2:
        return False

    raise AppError(
        code="remote-branch-check-failed",
        message="failed to verify whether branch exists on remote",
        details=result.stderr.strip() or result.stdout.strip() or f"{remote}/{branch}",
        guidance=("retry after confirming remote connectivity",),
    )


def _branch_exists(*, cwd: Path, branch: str, remote: str | None) -> bool:
    if _local_branch_exists(cwd=cwd, branch=branch):
        return True
    if remote is None:
        return False
    return _remote_branch_exists(cwd=cwd, branch=branch, remote=remote)


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


def _create_octopus_merge_commit(
    *, cwd: Path, branch: str, merge_parents: list[str]
) -> None:
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
                "resolve conflicts and commit the merge, or run `git merge --abort`",
                "rerun `gitcuttle new` once git status is clean",
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
