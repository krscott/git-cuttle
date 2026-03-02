import subprocess
from pathlib import Path

import pytest

from git_cuttle.metadata_manager import RepoMetadata, WorkspaceMetadata
from git_cuttle.remote_status import (
    PullRequestStatus,
    RemoteAheadBehindStatus,
    RemoteStatusCache,
    pull_request_status_for_repo,
    pull_request_status_for_workspace,
    remote_ahead_behind_for_repo,
    remote_ahead_behind_for_workspace,
)


def _git(*, cwd: Path, args: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        check=check,
        capture_output=True,
        text=True,
        cwd=cwd,
    )


def _workspace(branch: str, *, tracked_remote: str | None) -> WorkspaceMetadata:
    return WorkspaceMetadata(
        branch=branch,
        worktree_path=Path("/tmp/worktree"),
        tracked_remote=tracked_remote,
        kind="standard",
        base_ref="main",
        octopus_parents=(),
        created_at="2026-03-02T00:00:00Z",
        updated_at="2026-03-02T00:00:00Z",
    )


def _init_repo(path: Path) -> None:
    _git(cwd=path, args=["init", "-b", "main"])
    _git(cwd=path, args=["config", "user.name", "Test User"])
    _git(cwd=path, args=["config", "user.email", "test@example.com"])


def test_remote_ahead_behind_reports_unknown_without_remote(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    (repo / "README.md").write_text("hello\n")
    _git(cwd=repo, args=["add", "README.md"])
    _git(cwd=repo, args=["commit", "-m", "init"])

    status = remote_ahead_behind_for_workspace(
        repo_root=repo,
        workspace=_workspace("main", tracked_remote=None),
        default_remote=None,
    )

    assert status.upstream_ref is None
    assert status.ahead is None
    assert status.behind is None
    assert not status.known


def test_remote_ahead_behind_reports_unknown_when_remote_branch_is_missing(tmp_path: Path) -> None:
    remote = tmp_path / "remote.git"
    _git(cwd=tmp_path, args=["init", "--bare", str(remote)])

    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    (repo / "README.md").write_text("hello\n")
    _git(cwd=repo, args=["add", "README.md"])
    _git(cwd=repo, args=["commit", "-m", "init"])
    _git(cwd=repo, args=["remote", "add", "origin", str(remote)])
    _git(cwd=repo, args=["push", "-u", "origin", "main"])
    _git(cwd=repo, args=["checkout", "-b", "feature"])

    status = remote_ahead_behind_for_workspace(
        repo_root=repo,
        workspace=_workspace("feature", tracked_remote="origin"),
        default_remote="origin",
    )

    assert status.upstream_ref == "origin/feature"
    assert status.ahead is None
    assert status.behind is None
    assert not status.known


def test_remote_ahead_behind_counts_diverged_branch(tmp_path: Path) -> None:
    remote = tmp_path / "remote.git"
    _git(cwd=tmp_path, args=["init", "--bare", str(remote)])

    source = tmp_path / "source"
    source.mkdir()
    _init_repo(source)
    (source / "README.md").write_text("base\n")
    _git(cwd=source, args=["add", "README.md"])
    _git(cwd=source, args=["commit", "-m", "init"])
    _git(cwd=source, args=["remote", "add", "origin", str(remote)])
    _git(cwd=source, args=["push", "-u", "origin", "main"])
    _git(cwd=source, args=["checkout", "-b", "feature"])
    (source / "feature.txt").write_text("feature\n")
    _git(cwd=source, args=["add", "feature.txt"])
    _git(cwd=source, args=["commit", "-m", "feature start"])
    _git(cwd=source, args=["push", "-u", "origin", "feature"])

    repo = tmp_path / "repo"
    _git(cwd=tmp_path, args=["clone", str(remote), str(repo)])
    _git(cwd=repo, args=["config", "user.name", "Test User"])
    _git(cwd=repo, args=["config", "user.email", "test@example.com"])
    _git(cwd=repo, args=["checkout", "feature"])

    (repo / "local.txt").write_text("local\n")
    _git(cwd=repo, args=["add", "local.txt"])
    _git(cwd=repo, args=["commit", "-m", "local commit"])

    _git(cwd=source, args=["checkout", "feature"])
    (source / "remote.txt").write_text("remote\n")
    _git(cwd=source, args=["add", "remote.txt"])
    _git(cwd=source, args=["commit", "-m", "remote commit"])
    _git(cwd=source, args=["push", "origin", "feature"])
    _git(cwd=repo, args=["fetch", "origin"])

    repo_metadata = RepoMetadata(
        git_dir=(repo / ".git").resolve(strict=False),
        repo_root=repo.resolve(strict=False),
        default_remote="origin",
        tracked_at="2026-03-02T00:00:00Z",
        updated_at="2026-03-02T00:00:00Z",
        workspaces={
            "feature": _workspace("feature", tracked_remote="origin"),
        },
    )

    statuses = remote_ahead_behind_for_repo(repo=repo_metadata)
    status = statuses["feature"]
    assert status.upstream_ref == "origin/feature"
    assert status.ahead == 1
    assert status.behind == 1
    assert status.known


def test_remote_status_cache_reuses_value_within_ttl(tmp_path: Path) -> None:
    now_values = iter([100.0, 120.0])
    cache = RemoteStatusCache(now=lambda: next(now_values))
    repo = RepoMetadata(
        git_dir=(tmp_path / "repo.git").resolve(strict=False),
        repo_root=(tmp_path / "repo").resolve(strict=False),
        default_remote="origin",
        tracked_at="2026-03-02T00:00:00Z",
        updated_at="2026-03-02T00:00:00Z",
        workspaces={},
    )
    calls = {"count": 0}

    def resolver(_: RepoMetadata) -> dict[str, RemoteAheadBehindStatus]:
        calls["count"] += 1
        return {
            "feature": RemoteAheadBehindStatus(
                branch="feature",
                upstream_ref="origin/feature",
                ahead=calls["count"],
                behind=0,
            )
        }

    first = cache.statuses_for_repo(repo=repo, resolver=resolver)
    second = cache.statuses_for_repo(repo=repo, resolver=resolver)

    assert calls["count"] == 1
    assert first["feature"].ahead == 1
    assert second["feature"].ahead == 1


def test_remote_status_cache_refreshes_after_ttl(tmp_path: Path) -> None:
    now_values = iter([100.0, 161.0])
    cache = RemoteStatusCache(now=lambda: next(now_values))
    repo = RepoMetadata(
        git_dir=(tmp_path / "repo.git").resolve(strict=False),
        repo_root=(tmp_path / "repo").resolve(strict=False),
        default_remote="origin",
        tracked_at="2026-03-02T00:00:00Z",
        updated_at="2026-03-02T00:00:00Z",
        workspaces={},
    )
    calls = {"count": 0}

    def resolver(_: RepoMetadata) -> dict[str, RemoteAheadBehindStatus]:
        calls["count"] += 1
        return {
            "feature": RemoteAheadBehindStatus(
                branch="feature",
                upstream_ref="origin/feature",
                ahead=calls["count"],
                behind=0,
            )
        }

    first = cache.statuses_for_repo(repo=repo, resolver=resolver)
    second = cache.statuses_for_repo(repo=repo, resolver=resolver)

    assert calls["count"] == 2
    assert first["feature"].ahead == 1
    assert second["feature"].ahead == 2


def test_pull_request_status_for_workspace_returns_unknown_without_upstream(
    tmp_path: Path,
) -> None:
    status = pull_request_status_for_workspace(
        repo_root=tmp_path,
        workspace=_workspace("feature", tracked_remote=None),
        default_remote=None,
    )

    assert status.state == "unknown"
    assert status.title is None
    assert status.url is None
    assert not status.known


def test_pull_request_status_for_workspace_reads_open_pr_from_gh(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(
        args: list[str],
        *,
        capture_output: bool,
        text: bool,
        check: bool,
        cwd: Path,
    ) -> subprocess.CompletedProcess[str]:
        _ = capture_output
        _ = text
        _ = check
        _ = cwd
        if args == ["git", "remote", "get-url", "origin"]:
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="git@github.com:acme/repo.git\n")
        if args[:3] == ["gh", "pr", "list"]:
            return subprocess.CompletedProcess(
                args=args,
                returncode=0,
                stdout='[{"state":"OPEN","title":"Add feature","url":"https://github.com/acme/repo/pull/42"}]',
            )
        raise AssertionError(f"unexpected command: {args}")

    monkeypatch.setattr(subprocess, "run", fake_run)

    status = pull_request_status_for_workspace(
        repo_root=tmp_path,
        workspace=_workspace("feature", tracked_remote="origin"),
        default_remote="origin",
    )

    assert status == PullRequestStatus(
        branch="feature",
        upstream_ref="origin/feature",
        state="open",
        title="Add feature",
        url="https://github.com/acme/repo/pull/42",
    )
    assert status.known


def test_pull_request_status_for_workspace_returns_unknown_when_no_pr(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(
        args: list[str],
        *,
        capture_output: bool,
        text: bool,
        check: bool,
        cwd: Path,
    ) -> subprocess.CompletedProcess[str]:
        _ = capture_output
        _ = text
        _ = check
        _ = cwd
        if args == ["git", "remote", "get-url", "origin"]:
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="https://github.com/acme/repo.git\n")
        if args[:3] == ["gh", "pr", "list"]:
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="[]")
        raise AssertionError(f"unexpected command: {args}")

    monkeypatch.setattr(subprocess, "run", fake_run)

    status = pull_request_status_for_workspace(
        repo_root=tmp_path,
        workspace=_workspace("feature", tracked_remote="origin"),
        default_remote="origin",
    )

    assert status.state == "unknown"
    assert status.title is None
    assert status.url is None


def test_pull_request_status_for_workspace_is_unavailable_without_gh(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(
        args: list[str],
        *,
        capture_output: bool,
        text: bool,
        check: bool,
        cwd: Path,
    ) -> subprocess.CompletedProcess[str]:
        _ = capture_output
        _ = text
        _ = check
        _ = cwd
        if args == ["git", "remote", "get-url", "origin"]:
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="https://github.com/acme/repo.git\n")
        if args[:3] == ["gh", "pr", "list"]:
            raise FileNotFoundError("gh")
        raise AssertionError(f"unexpected command: {args}")

    monkeypatch.setattr(subprocess, "run", fake_run)

    status = pull_request_status_for_workspace(
        repo_root=tmp_path,
        workspace=_workspace("feature", tracked_remote="origin"),
        default_remote="origin",
    )

    assert status.state == "unavailable"
    assert status.title is None
    assert status.url is None


def test_pull_request_status_for_repo_maps_each_workspace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = RepoMetadata(
        git_dir=(tmp_path / "repo.git").resolve(strict=False),
        repo_root=tmp_path.resolve(strict=False),
        default_remote="origin",
        tracked_at="2026-03-02T00:00:00Z",
        updated_at="2026-03-02T00:00:00Z",
        workspaces={
            "feature-a": _workspace("feature-a", tracked_remote="origin"),
            "feature-b": _workspace("feature-b", tracked_remote="origin"),
        },
    )

    def fake_run(
        args: list[str],
        *,
        capture_output: bool,
        text: bool,
        check: bool,
        cwd: Path,
    ) -> subprocess.CompletedProcess[str]:
        _ = capture_output
        _ = text
        _ = check
        _ = cwd
        if args == ["git", "remote", "get-url", "origin"]:
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="https://github.com/acme/repo.git\n")
        if args[:3] == ["gh", "pr", "list"] and "feature-a" in args:
            return subprocess.CompletedProcess(
                args=args,
                returncode=0,
                stdout='[{"state":"MERGED","title":"A","url":"https://github.com/acme/repo/pull/1"}]',
            )
        if args[:3] == ["gh", "pr", "list"] and "feature-b" in args:
            return subprocess.CompletedProcess(
                args=args,
                returncode=0,
                stdout='[{"state":"CLOSED","title":"B","url":"https://github.com/acme/repo/pull/2"}]',
            )
        raise AssertionError(f"unexpected command: {args}")

    monkeypatch.setattr(subprocess, "run", fake_run)

    statuses = pull_request_status_for_repo(repo=repo)

    assert statuses["feature-a"].state == "merged"
    assert statuses["feature-b"].state == "closed"
