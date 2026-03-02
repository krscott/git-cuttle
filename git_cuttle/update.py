import subprocess
from dataclasses import dataclass
from pathlib import Path

from git_cuttle.errors import AppError
from git_cuttle.metadata_manager import WorkspaceMetadata


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
            guidance=(
                "push the upstream branch or configure a different upstream",
            ),
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

    updated_parent_refs = tuple(
        _update_octopus_parent(
            repo_root=repo_root,
            parent_ref=parent_ref,
        )
        for parent_ref in workspace.octopus_parents
    )

    before_oid = _branch_head(repo_root=repo_root, branch=workspace.branch)
    replay_commits = _octopus_replay_commits(
        repo_root=repo_root,
        branch=workspace.branch,
        parent_refs=updated_parent_refs,
    )

    _checkout_branch(repo_root=repo_root, branch=workspace.branch)
    try:
        try:
            _git(
                repo_root=repo_root,
                args=["reset", "--hard", updated_parent_refs[0]],
                code="octopus-update-reset-failed",
                message="failed to reset octopus workspace branch to first parent",
            )
            _git(
                repo_root=repo_root,
                args=[
                    "merge",
                    "--no-ff",
                    "-m",
                    f"Rebuild octopus workspace {workspace.branch}",
                    *updated_parent_refs[1:],
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
            _restore_octopus_branch_after_failure(
                repo_root=repo_root,
                branch=workspace.branch,
                original_oid=before_oid,
                cause=error,
            )
            raise
    finally:
        if original_branch is not None and original_branch != workspace.branch:
            _checkout_branch(repo_root=repo_root, branch=original_branch)

    after_oid = _branch_head(repo_root=repo_root, branch=workspace.branch)
    return OctopusUpdateResult(
        branch=workspace.branch,
        before_oid=before_oid,
        after_oid=after_oid,
        parent_refs=updated_parent_refs,
        replayed_commits=tuple(replay_commits),
    )


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


def _update_octopus_parent(
    *, repo_root: Path, parent_ref: str
) -> str:
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
            message=(
                f"failed to rebase octopus parent {parent_ref} onto upstream"
            ),
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


def _restore_octopus_branch_after_failure(
    *,
    repo_root: Path,
    branch: str,
    original_oid: str,
    cause: AppError,
) -> None:
    try:
        _git(
            repo_root=repo_root,
            args=["reset", "--hard", original_oid],
            code="octopus-update-rollback-failed",
            message="failed to restore octopus workspace branch after update failure",
        )
    except AppError as rollback_error:
        cause_details = cause.details or cause.message
        rollback_details = rollback_error.details or rollback_error.message
        raise AppError(
            code="octopus-update-rollback-failed",
            message="octopus update failed and rollback could not restore the branch",
            details=(
                f"update error [{cause.code}]: {cause_details}; "
                f"rollback error: {rollback_details}"
            ),
            guidance=(
                f"checkout {branch} and run `git reset --hard {original_oid}` to recover",
            ),
        ) from cause


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
        ["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", f"{branch}@{{upstream}}"],
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
