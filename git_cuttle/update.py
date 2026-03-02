from dataclasses import dataclass
from pathlib import Path
import subprocess

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

    upstream_ref = _workspace_upstream_ref(workspace=workspace, default_remote=default_remote)
    if upstream_ref is None:
        raise AppError(
            code="no-upstream",
            message="workspace has no upstream remote branch configured",
            details=workspace.branch,
            guidance=(
                "set tracked_remote metadata or configure a default remote for this repository",
            ),
        )

    remote_name = upstream_ref.split("/", maxsplit=1)[0]
    _git(repo_root=repo_root, args=["fetch", remote_name], code="update-fetch-failed", message="failed to fetch upstream")

    if _rev_parse(repo_root=repo_root, ref=f"refs/remotes/{upstream_ref}") is None:
        raise AppError(
            code="no-upstream",
            message="workspace upstream remote branch does not exist",
            details=upstream_ref,
            guidance=("push the branch to the remote or configure a different upstream",),
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

    remote_name = workspace.tracked_remote or default_remote
    if remote_name is not None:
        _git(
            repo_root=repo_root,
            args=["fetch", remote_name],
            code="update-fetch-failed",
            message="failed to fetch octopus parent refs",
        )

    resolved_parent_refs = tuple(
        _resolve_octopus_parent_ref(
            repo_root=repo_root,
            remote_name=remote_name,
            parent_ref=parent_ref,
        )
        for parent_ref in workspace.octopus_parents
    )

    before_oid = _branch_head(repo_root=repo_root, branch=workspace.branch)
    replay_commits = _octopus_replay_commits(
        repo_root=repo_root,
        branch=workspace.branch,
        parent_refs=resolved_parent_refs,
    )

    original_branch = _current_branch(repo_root=repo_root)
    _checkout_branch(repo_root=repo_root, branch=workspace.branch)
    try:
        _git(
            repo_root=repo_root,
            args=["reset", "--hard", resolved_parent_refs[0]],
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
                *resolved_parent_refs[1:],
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
    finally:
        if original_branch is not None and original_branch != workspace.branch:
            _checkout_branch(repo_root=repo_root, branch=original_branch)

    after_oid = _branch_head(repo_root=repo_root, branch=workspace.branch)
    return OctopusUpdateResult(
        branch=workspace.branch,
        before_oid=before_oid,
        after_oid=after_oid,
        parent_refs=resolved_parent_refs,
        replayed_commits=tuple(replay_commits),
    )


def _workspace_upstream_ref(*, workspace: WorkspaceMetadata, default_remote: str | None) -> str | None:
    remote_name = workspace.tracked_remote or default_remote
    if remote_name is None:
        return None
    return f"{remote_name}/{workspace.branch}"


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


def _resolve_octopus_parent_ref(*, repo_root: Path, remote_name: str | None, parent_ref: str) -> str:
    if remote_name is not None:
        remote_tracking_ref = f"refs/remotes/{remote_name}/{parent_ref}"
        if _rev_parse(repo_root=repo_root, ref=remote_tracking_ref) is not None:
            return f"{remote_name}/{parent_ref}"

    local_ref = f"refs/heads/{parent_ref}"
    if _rev_parse(repo_root=repo_root, ref=local_ref) is not None:
        return parent_ref

    raise AppError(
        code="octopus-parent-missing",
        message="octopus parent ref does not exist",
        details=parent_ref,
        guidance=("fetch the missing parent branch or update workspace metadata",),
    )


def _octopus_replay_commits(*, repo_root: Path, branch: str, parent_refs: tuple[str, ...]) -> list[str]:
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


def _is_merge_commit(*, repo_root: Path, commit: str) -> bool:
    parent_line = _git_stdout(repo_root=repo_root, args=["show", "-s", "--format=%P", commit])
    parent_oids = [parent for parent in parent_line.split() if parent]
    return len(parent_oids) > 1


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
        raise AppError(code=code, message=message, details=details)


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
