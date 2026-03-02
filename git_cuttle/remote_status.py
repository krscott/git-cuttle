from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
import time
from typing import Callable, Literal, cast
from urllib.parse import urlparse

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


PrState = Literal["open", "closed", "merged", "unknown", "unavailable"]


@dataclass(kw_only=True, frozen=True)
class PullRequestStatus:
    branch: str
    upstream_ref: str | None
    state: PrState
    title: str | None
    url: str | None

    @property
    def known(self) -> bool:
        return self.state in {"open", "closed", "merged"}


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


def pull_request_status_for_repo(*, repo: RepoMetadata) -> dict[str, PullRequestStatus]:
    statuses: dict[str, PullRequestStatus] = {}
    for branch, workspace in repo.workspaces.items():
        statuses[branch] = pull_request_status_for_workspace(
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


def pull_request_status_for_workspace(
    *,
    repo_root: Path,
    workspace: WorkspaceMetadata,
    default_remote: str | None,
) -> PullRequestStatus:
    upstream_ref = _workspace_upstream_ref(workspace=workspace, default_remote=default_remote)
    unknown = PullRequestStatus(
        branch=workspace.branch,
        upstream_ref=upstream_ref,
        state="unknown",
        title=None,
        url=None,
    )
    if upstream_ref is None:
        return unknown

    remote_name = workspace.tracked_remote or default_remote
    if remote_name is None:
        return unknown

    repo_slug = _github_repo_slug_for_remote(repo_root=repo_root, remote_name=remote_name)
    if repo_slug is None:
        return PullRequestStatus(
            branch=workspace.branch,
            upstream_ref=upstream_ref,
            state="unavailable",
            title=None,
            url=None,
        )

    return _pull_request_status_from_gh(
        repo_root=repo_root,
        branch=workspace.branch,
        upstream_ref=upstream_ref,
        repo_slug=repo_slug,
    )


def _workspace_upstream_ref(*, workspace: WorkspaceMetadata, default_remote: str | None) -> str | None:
    remote_name = workspace.tracked_remote or default_remote
    if remote_name is None:
        return None
    return f"{remote_name}/{workspace.branch}"


def _github_repo_slug_for_remote(*, repo_root: Path, remote_name: str) -> str | None:
    result = subprocess.run(
        ["git", "remote", "get-url", remote_name],
        capture_output=True,
        text=True,
        check=False,
        cwd=repo_root,
    )
    if result.returncode != 0:
        return None
    return _github_repo_slug_from_url(result.stdout.strip())


def _github_repo_slug_from_url(remote_url: str) -> str | None:
    normalized = remote_url.strip()
    if not normalized:
        return None
    if normalized.endswith(".git"):
        normalized = normalized[: -len(".git")]

    path: str | None = None
    if normalized.startswith("git@github.com:"):
        path = normalized[len("git@github.com:") :]
    elif normalized.startswith("ssh://git@github.com/"):
        path = normalized[len("ssh://git@github.com/") :]
    else:
        parsed = urlparse(normalized)
        if parsed.hostname == "github.com":
            path = parsed.path.lstrip("/")

    if path is None:
        return None

    parts = [part for part in path.split("/") if part]
    if len(parts) != 2:
        return None
    owner, repo = parts
    return f"{owner}/{repo}"


def _pull_request_status_from_gh(
    *,
    repo_root: Path,
    branch: str,
    upstream_ref: str,
    repo_slug: str,
) -> PullRequestStatus:
    try:
        result = subprocess.run(
            [
                "gh",
                "pr",
                "list",
                "--repo",
                repo_slug,
                "--head",
                branch,
                "--state",
                "all",
                "--json",
                "state,title,url",
                "--limit",
                "1",
            ],
            capture_output=True,
            text=True,
            check=False,
            cwd=repo_root,
        )
    except FileNotFoundError:
        return PullRequestStatus(
            branch=branch,
            upstream_ref=upstream_ref,
            state="unavailable",
            title=None,
            url=None,
        )

    if result.returncode != 0:
        return PullRequestStatus(
            branch=branch,
            upstream_ref=upstream_ref,
            state="unavailable",
            title=None,
            url=None,
        )

    try:
        payload: object = json.loads(result.stdout)
    except json.JSONDecodeError:
        return PullRequestStatus(
            branch=branch,
            upstream_ref=upstream_ref,
            state="unavailable",
            title=None,
            url=None,
        )

    if not isinstance(payload, list) or not payload:
        return PullRequestStatus(
            branch=branch,
            upstream_ref=upstream_ref,
            state="unknown",
            title=None,
            url=None,
        )

    payload_list = cast(list[object], payload)
    first_raw = payload_list[0]
    if not isinstance(first_raw, dict):
        return PullRequestStatus(
            branch=branch,
            upstream_ref=upstream_ref,
            state="unavailable",
            title=None,
            url=None,
        )
    first = cast(dict[str, object], first_raw)

    state_raw = first.get("state")
    title = first.get("title")
    url = first.get("url")
    state_map: dict[str, PrState] = {
        "OPEN": "open",
        "CLOSED": "closed",
        "MERGED": "merged",
    }
    mapped_state = state_map.get(state_raw if isinstance(state_raw, str) else "", "unknown")

    return PullRequestStatus(
        branch=branch,
        upstream_ref=upstream_ref,
        state=mapped_state,
        title=title if isinstance(title, str) else None,
        url=url if isinstance(url, str) else None,
    )


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
