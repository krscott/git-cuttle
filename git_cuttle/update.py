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
