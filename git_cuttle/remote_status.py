from dataclasses import dataclass
from pathlib import Path
import subprocess
import time
from typing import Callable

from git_cuttle.metadata_manager import RepoMetadata, WorkspaceMetadata


@dataclass(kw_only=True, frozen=True)
class RemoteAheadBehindStatus:
    branch: str
    upstream_ref: str | None
    ahead: int | None
    behind: int | None

    @property
    def known(self) -> bool:
        return self.ahead is not None and self.behind is not None


StatusResolver = Callable[[RepoMetadata], dict[str, "RemoteAheadBehindStatus"]]


def _default_repo_status_resolver(repo: RepoMetadata) -> dict[str, RemoteAheadBehindStatus]:
    return remote_ahead_behind_for_repo(repo=repo)


@dataclass(kw_only=True)
class RemoteStatusCache:
    ttl_seconds: float = 60.0
    now: Callable[[], float] = time.time

    def __post_init__(self) -> None:
        self._entries: dict[str, tuple[float, dict[str, RemoteAheadBehindStatus]]] = {}

    def statuses_for_repo(
        self,
        *,
        repo: RepoMetadata,
        resolver: StatusResolver = _default_repo_status_resolver,
    ) -> dict[str, RemoteAheadBehindStatus]:
        cache_key = str(repo.git_dir)
        cached = self._entries.get(cache_key)
        now = self.now()
        if cached is not None:
            fetched_at, statuses = cached
            if now - fetched_at < self.ttl_seconds:
                return statuses

        statuses = resolver(repo)
        self._entries[cache_key] = (now, statuses)
        return statuses


def remote_ahead_behind_for_repo(*, repo: RepoMetadata) -> dict[str, RemoteAheadBehindStatus]:
    statuses: dict[str, RemoteAheadBehindStatus] = {}
    for branch, workspace in repo.workspaces.items():
        statuses[branch] = remote_ahead_behind_for_workspace(
            repo_root=repo.repo_root,
            workspace=workspace,
            default_remote=repo.default_remote,
        )
    return statuses


def remote_ahead_behind_for_workspace(
    *,
    repo_root: Path,
    workspace: WorkspaceMetadata,
    default_remote: str | None,
) -> RemoteAheadBehindStatus:
    upstream_ref = _workspace_upstream_ref(workspace=workspace, default_remote=default_remote)
    unknown = RemoteAheadBehindStatus(
        branch=workspace.branch,
        upstream_ref=upstream_ref,
        ahead=None,
        behind=None,
    )
    if upstream_ref is None:
        return unknown

    local_ref = f"refs/heads/{workspace.branch}"
    remote_ref = f"refs/remotes/{upstream_ref}"
    if not _ref_exists(repo_root=repo_root, ref=local_ref):
        return unknown
    if not _ref_exists(repo_root=repo_root, ref=remote_ref):
        return unknown

    counts = _ahead_behind_counts(repo_root=repo_root, local_branch=workspace.branch, upstream_ref=upstream_ref)
    if counts is None:
        return unknown

    ahead, behind = counts
    return RemoteAheadBehindStatus(
        branch=workspace.branch,
        upstream_ref=upstream_ref,
        ahead=ahead,
        behind=behind,
    )


def _workspace_upstream_ref(*, workspace: WorkspaceMetadata, default_remote: str | None) -> str | None:
    remote_name = workspace.tracked_remote or default_remote
    if remote_name is None:
        return None
    return f"{remote_name}/{workspace.branch}"


def _ref_exists(*, repo_root: Path, ref: str) -> bool:
    result = subprocess.run(
        ["git", "rev-parse", "--verify", ref],
        capture_output=True,
        text=True,
        check=False,
        cwd=repo_root,
    )
    return result.returncode == 0


def _ahead_behind_counts(*, repo_root: Path, local_branch: str, upstream_ref: str) -> tuple[int, int] | None:
    result = subprocess.run(
        ["git", "rev-list", "--left-right", "--count", f"{local_branch}...{upstream_ref}"],
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
        ahead = int(parts[0])
        behind = int(parts[1])
    except ValueError:
        return None

    return ahead, behind
