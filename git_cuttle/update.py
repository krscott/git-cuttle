import subprocess
from dataclasses import dataclass
from pathlib import Path

from git_cuttle.errors import AppError
from git_cuttle.git_ops import (
    backup_ref_for_branch,
    create_backup_refs_for_branches,
    remove_backup_refs,
)
from git_cuttle.metadata_manager import WorkspaceMetadata
from git_cuttle.transaction import (
    Transaction,
    TransactionExecutionError,
    TransactionStep,
)


@dataclass(kw_only=True, frozen=True)
class UpdateResult:
    branch: str
    upstream_ref: str
    before_oid: str
    after_oid: str

    @property
    def changed(self) -> bool:
        return self.before_oid != self.after_oid


@dataclass(kw_only=True, frozen=True)
class OctopusUpdateResult:
    branch: str
    before_oid: str
    after_oid: str
    parent_refs: tuple[str, ...]
    replayed_commits: tuple[str, ...]

    @property
    def changed(self) -> bool:
        return self.before_oid != self.after_oid


def update_non_octopus_workspace(
    *,
    repo_root: Path,
    workspace: WorkspaceMetadata,
    default_remote: str | None,
) -> UpdateResult:
    if workspace.kind != "standard":
        raise AppError(
            code="octopus-update-not-supported",
            message="octopus workspaces require the octopus update flow",
            guidance=("run octopus-specific update once implemented",),
        )

    upstream_ref = _branch_upstream_ref(repo_root=repo_root, branch=workspace.branch)
    if upstream_ref is None:
        raise AppError(
            code="no-upstream",
            message="workspace has no upstream remote branch configured",
            details=workspace.branch,
            guidance=(
                f"run `git branch --set-upstream-to <remote>/<branch> {workspace.branch}` and retry",
            ),
        )

    remote_name = _remote_name_for_ref(repo_root=repo_root, ref=upstream_ref)
    if remote_name is not None:
        _git(
            repo_root=repo_root,
            args=["fetch", remote_name],
            code="update-fetch-failed",
            message="failed to fetch upstream",
        )

    if _rev_parse(repo_root=repo_root, ref=upstream_ref) is None:
        raise AppError(
            code="no-upstream",
            message="workspace upstream branch does not exist",
            details=upstream_ref,
            guidance=("push the upstream branch or configure a different upstream",),
        )

    before_oid = _branch_head(repo_root=repo_root, branch=workspace.branch)
    _git(
        repo_root=repo_root,
        args=["rebase", upstream_ref, workspace.branch],
        code="update-rebase-failed",
        message="failed to rebase branch onto upstream",
    )
    after_oid = _branch_head(repo_root=repo_root, branch=workspace.branch)

    return UpdateResult(
        branch=workspace.branch,
        upstream_ref=upstream_ref,
        before_oid=before_oid,
        after_oid=after_oid,
    )


def update_octopus_workspace(
    *,
    repo_root: Path,
    workspace: WorkspaceMetadata,
    default_remote: str | None,
) -> OctopusUpdateResult:
    if workspace.kind != "octopus":
        raise AppError(
            code="invalid-workspace-kind",
            message="octopus update requires octopus workspace metadata",
            details=workspace.branch,
        )
    if len(workspace.octopus_parents) < 2:
        raise AppError(
            code="invalid-octopus-parents",
            message="octopus workspace must track at least two parent refs",
            details=workspace.branch,
        )

    _ensure_workspace_clean_for_octopus_update(workspace=workspace)
    original_branch = _current_branch(repo_root=repo_root)
    before_oid = _branch_head(repo_root=repo_root, branch=workspace.branch)
    updated_parent_refs = tuple(workspace.octopus_parents)
    replay_commits: list[str] = []
    touched_branches = (*workspace.octopus_parents, workspace.branch)
    transaction = Transaction()

    transaction.add_step(
        _backup_refs_step(
            repo_root=repo_root,
            transaction=transaction,
            branches=touched_branches,
        )
    )
    for parent_ref in workspace.octopus_parents:
        transaction.add_step(
            _update_parent_step(
                repo_root=repo_root,
                transaction=transaction,
                parent_ref=parent_ref,
            )
        )
    transaction.add_step(
        _rebuild_octopus_step(
            repo_root=repo_root,
            transaction=transaction,
            workspace=workspace,
            replay_commits=replay_commits,
            parent_refs=updated_parent_refs,
        )
    )
    transaction.add_step(
        _cleanup_backup_refs_step(
            repo_root=repo_root,
            transaction=transaction,
            branches=touched_branches,
        )
    )

    try:
        try:
            transaction.run()
        except TransactionExecutionError as error:
            if isinstance(error.cause, AppError):
                raise error.cause
            raise AppError(
                code="octopus-update-failed",
                message="octopus update failed",
                details=str(error.cause),
            ) from error
    finally:
        current_branch = _current_branch(repo_root=repo_root)
        if (
            original_branch is not None
            and current_branch is not None
            and original_branch != current_branch
        ):
            _checkout_branch(repo_root=repo_root, branch=original_branch)

    after_oid = _branch_head(repo_root=repo_root, branch=workspace.branch)
    return OctopusUpdateResult(
        branch=workspace.branch,
        before_oid=before_oid,
        after_oid=after_oid,
        parent_refs=updated_parent_refs,
        replayed_commits=tuple(replay_commits),
    )


def _backup_refs_step(
    *,
    repo_root: Path,
    transaction: Transaction,
    branches: tuple[str, ...],
) -> TransactionStep:

    unique_branches = tuple(dict.fromkeys(branches))
    recovery_commands = tuple(
        _restore_backup_command(txn_id=transaction.txn_id, branch=branch)
        for branch in unique_branches
    )
    return TransactionStep(
        name="backup-refs",
        apply=lambda: _create_backup_refs(
            repo_root=repo_root,
            txn_id=transaction.txn_id,
            branches=unique_branches,
        ),
        rollback=lambda: remove_backup_refs(txn_id=transaction.txn_id, cwd=repo_root),
        recovery_commands=recovery_commands,
    )


def _update_parent_step(
    *,
    repo_root: Path,
    transaction: Transaction,
    parent_ref: str,
) -> TransactionStep:
    def apply_parent_update() -> None:
        _update_octopus_parent(repo_root=repo_root, parent_ref=parent_ref)

    return TransactionStep(
        name=f"update-parent:{parent_ref}",
        apply=apply_parent_update,
        rollback=lambda: _restore_branch_from_backup_ref(
            repo_root=repo_root,
            txn_id=transaction.txn_id,
            branch=parent_ref,
        ),
        recovery_commands=(
            _restore_backup_command(txn_id=transaction.txn_id, branch=parent_ref),
        ),
    )


def _rebuild_octopus_step(
    *,
    repo_root: Path,
    transaction: Transaction,
    workspace: WorkspaceMetadata,
    replay_commits: list[str],
    parent_refs: tuple[str, ...],
) -> TransactionStep:

    return TransactionStep(
        name=f"rebuild-octopus:{workspace.branch}",
        apply=lambda: _rebuild_octopus_branch(
            repo_root=repo_root,
            txn_id=transaction.txn_id,
            branch=workspace.branch,
            parent_refs=parent_refs,
            replay_commits=replay_commits,
        ),
        rollback=lambda: _restore_branch_from_backup_ref(
            repo_root=repo_root,
            txn_id=transaction.txn_id,
            branch=workspace.branch,
        ),
        recovery_commands=(
            _restore_backup_command(txn_id=transaction.txn_id, branch=workspace.branch),
        ),
    )


def _cleanup_backup_refs_step(
    *,
    repo_root: Path,
    transaction: Transaction,
    branches: tuple[str, ...],
) -> TransactionStep:

    unique_branches = tuple(dict.fromkeys(branches))
    return TransactionStep(
        name="cleanup-backup-refs",
        apply=lambda: remove_backup_refs(txn_id=transaction.txn_id, cwd=repo_root),
        rollback=lambda: None,
        recovery_commands=tuple(
            _delete_backup_ref_command(txn_id=transaction.txn_id, branch=branch)
            for branch in unique_branches
        ),
    )


def _create_backup_refs(
    *,
    repo_root: Path,
    txn_id: str,
    branches: tuple[str, ...],
) -> None:
    try:
        _ = create_backup_refs_for_branches(
            txn_id=txn_id,
            branches=list(branches),
            cwd=repo_root,
        )
    except RuntimeError as error:
        raise AppError(
            code="octopus-update-backup-failed",
            message="failed to create transactional backup refs for octopus update",
            details=str(error),
        ) from error


def _rebuild_octopus_branch(
    *,
    repo_root: Path,
    txn_id: str,
    branch: str,
    parent_refs: tuple[str, ...],
    replay_commits: list[str],
) -> None:
    replay_commits.clear()
    replay_commits.extend(
        _octopus_replay_commits(
            repo_root=repo_root,
            branch=branch,
            parent_refs=parent_refs,
        )
    )

    try:
        _checkout_branch(repo_root=repo_root, branch=branch)
        _git(
            repo_root=repo_root,
            args=["reset", "--hard", parent_refs[0]],
            code="octopus-update-reset-failed",
            message="failed to reset octopus workspace branch to first parent",
        )
        _git(
            repo_root=repo_root,
            args=[
                "merge",
                "--no-ff",
                "-m",
                f"Rebuild octopus workspace {branch}",
                *parent_refs[1:],
            ],
            code="octopus-update-merge-failed",
            message="failed to rebuild octopus merge commit",
        )

        if replay_commits:
            _git(
                repo_root=repo_root,
                args=["cherry-pick", *replay_commits],
                code="octopus-update-replay-failed",
                message="failed to replay post-merge commits onto rebuilt octopus branch",
            )
    except AppError as error:
        try:
            _restore_branch_from_backup_ref(
                repo_root=repo_root,
                txn_id=txn_id,
                branch=branch,
            )
        except Exception as rollback_error:
            raise AppError(
                code="octopus-update-rollback-failed",
                message="octopus update failed and rollback could not restore workspace branch",
                details=(
                    f"update error [{error.code}]: {error.details or error.message}; "
                    f"rollback error: {rollback_error}"
                ),
                guidance=(_restore_backup_command(txn_id=txn_id, branch=branch),),
            ) from error
        raise


def _restore_branch_from_backup_ref(
    *, repo_root: Path, txn_id: str, branch: str
) -> None:
    backup_ref = backup_ref_for_branch(txn_id=txn_id, branch=branch)
    backup_oid = _rev_parse(repo_root=repo_root, ref=backup_ref)
    if backup_oid is None:
        raise RuntimeError(f"backup ref does not exist: {backup_ref}")

    _git(
        repo_root=repo_root,
        args=["reset", "--hard"],
        code="octopus-update-rollback-failed",
        message="failed to clear git state before restoring backup refs",
    )
    _checkout_branch(repo_root=repo_root, branch=branch)
    _git(
        repo_root=repo_root,
        args=["reset", "--hard", backup_oid],
        code="octopus-update-rollback-failed",
        message="failed to restore octopus branch from backup ref",
    )


def _restore_backup_command(*, txn_id: str, branch: str) -> str:
    backup_ref = backup_ref_for_branch(txn_id=txn_id, branch=branch)
    return f"git checkout {branch} && git reset --hard {backup_ref}"


def _delete_backup_ref_command(*, txn_id: str, branch: str) -> str:
    return f"git update-ref -d {backup_ref_for_branch(txn_id=txn_id, branch=branch)}"


def _branch_head(*, repo_root: Path, branch: str) -> str:
    branch_oid = _rev_parse(repo_root=repo_root, ref=f"refs/heads/{branch}")
    if branch_oid is None:
        raise AppError(
            code="branch-missing",
            message="workspace branch does not exist locally",
            details=branch,
            guidance=("fetch or recreate the local branch before running update",),
        )
    return branch_oid


def _update_octopus_parent(*, repo_root: Path, parent_ref: str) -> str:
    local_ref = f"refs/heads/{parent_ref}"
    if _rev_parse(repo_root=repo_root, ref=local_ref) is not None:
        upstream_ref = _branch_upstream_ref(repo_root=repo_root, branch=parent_ref)
        if upstream_ref is None:
            return parent_ref

        remote_name = _remote_name_for_ref(repo_root=repo_root, ref=upstream_ref)
        if remote_name is not None:
            _git(
                repo_root=repo_root,
                args=["fetch", remote_name],
                code="update-fetch-failed",
                message="failed to fetch octopus parent refs",
            )

        if _rev_parse(repo_root=repo_root, ref=upstream_ref) is None:
            raise AppError(
                code="octopus-parent-upstream-missing",
                message="octopus parent upstream branch does not exist",
                details=upstream_ref,
                guidance=(
                    "push the upstream branch or configure a different upstream",
                ),
            )

        _git(
            repo_root=repo_root,
            args=["rebase", upstream_ref, parent_ref],
            code="octopus-parent-update-failed",
            message=(f"failed to rebase octopus parent {parent_ref} onto upstream"),
        )
        return parent_ref

    raise AppError(
        code="octopus-parent-missing",
        message="octopus parent ref does not exist",
        details=parent_ref,
        guidance=("fetch the missing parent branch or update workspace metadata",),
    )


def _octopus_replay_commits(
    *, repo_root: Path, branch: str, parent_refs: tuple[str, ...]
) -> list[str]:
    result = subprocess.run(
        ["git", "rev-list", "--reverse", branch, "--not", *parent_refs],
        capture_output=True,
        text=True,
        check=False,
        cwd=repo_root,
    )
    if result.returncode != 0:
        details = result.stderr.strip() or result.stdout.strip() or branch
        raise AppError(
            code="octopus-update-analysis-failed",
            message="failed to analyze octopus branch history",
            details=details,
        )

    commits = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if not commits:
        return []

    if _is_merge_commit(repo_root=repo_root, commit=commits[0]):
        return commits[1:]
    return commits


def _ensure_workspace_clean_for_octopus_update(*, workspace: WorkspaceMetadata) -> None:
    worktree_path = workspace.worktree_path
    if not worktree_path.exists():
        return
    if not _worktree_has_uncommitted_changes(cwd=worktree_path):
        return

    raise AppError(
        code="workspace-dirty",
        message="workspace has uncommitted changes",
        details=str(worktree_path),
        guidance=("commit or stash changes, then retry update",),
    )


def _is_merge_commit(*, repo_root: Path, commit: str) -> bool:
    parent_line = _git_stdout(
        repo_root=repo_root, args=["show", "-s", "--format=%P", commit]
    )
    parent_oids = [parent for parent in parent_line.split() if parent]
    return len(parent_oids) > 1


def _worktree_has_uncommitted_changes(*, cwd: Path) -> bool:
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        capture_output=True,
        text=True,
        check=False,
        cwd=cwd,
    )
    return result.returncode == 0 and bool(result.stdout.strip())


def _current_branch(*, repo_root: Path) -> str | None:
    branch = _git_stdout(
        repo_root=repo_root,
        args=["rev-parse", "--abbrev-ref", "HEAD"],
        code="git-state-read-failed",
        message="failed to resolve current branch",
    )
    if branch == "" or branch == "HEAD":
        return None
    return branch


def _branch_upstream_ref(*, repo_root: Path, branch: str) -> str | None:
    result = subprocess.run(
        [
            "git",
            "rev-parse",
            "--abbrev-ref",
            "--symbolic-full-name",
            f"{branch}@{{upstream}}",
        ],
        capture_output=True,
        text=True,
        check=False,
        cwd=repo_root,
    )
    if result.returncode != 0:
        return None
    upstream_ref = result.stdout.strip()
    if upstream_ref == "":
        return None
    return upstream_ref


def _remote_name_for_ref(*, repo_root: Path, ref: str) -> str | None:
    if ref.startswith("refs/remotes/"):
        parts = ref.split("/", maxsplit=3)
        if len(parts) >= 3:
            candidate = parts[2]
            if _is_remote_name(repo_root=repo_root, name=candidate):
                return candidate
        return None

    candidate, _, _ = ref.partition("/")
    if candidate == "":
        return None
    if _is_remote_name(repo_root=repo_root, name=candidate):
        return candidate
    return None


def _is_remote_name(*, repo_root: Path, name: str) -> bool:
    result = subprocess.run(
        ["git", "remote"],
        capture_output=True,
        text=True,
        check=False,
        cwd=repo_root,
    )
    if result.returncode != 0:
        return False
    remote_names = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return name in remote_names


def _checkout_branch(*, repo_root: Path, branch: str) -> None:
    _git(
        repo_root=repo_root,
        args=["checkout", branch],
        code="branch-checkout-failed",
        message="failed to checkout branch",
    )


def _rev_parse(*, repo_root: Path, ref: str) -> str | None:
    result = subprocess.run(
        ["git", "rev-parse", "--verify", ref],
        capture_output=True,
        text=True,
        check=False,
        cwd=repo_root,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def _git(*, repo_root: Path, args: list[str], code: str, message: str) -> None:
    result = subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        check=False,
        cwd=repo_root,
    )
    if result.returncode != 0:
        details = result.stderr.strip() or result.stdout.strip() or " ".join(args)
        raise AppError(
            code=code,
            message=message,
            details=details,
            guidance=_git_failure_guidance(args=args),
        )


def _git_failure_guidance(*, args: list[str]) -> tuple[str, ...]:
    if not args:
        return ()

    command = args[0]
    if command == "rebase":
        return (
            "resolve conflicts, then run `git rebase --continue`",
            "or run `git rebase --abort` to restore a clean git state before retrying",
        )
    if command == "merge":
        return (
            "resolve conflicts and commit the merge, or run `git merge --abort`",
            "rerun `gitcuttle update` once git status is clean",
        )
    if command == "cherry-pick":
        return (
            "resolve conflicts, then run `git cherry-pick --continue`",
            "or run `git cherry-pick --abort` to restore a clean git state before retrying",
        )

    return ()


def _git_stdout(
    *,
    repo_root: Path,
    args: list[str],
    code: str = "git-command-failed",
    message: str = "git command failed",
) -> str:
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
