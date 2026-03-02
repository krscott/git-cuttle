import subprocess
from pathlib import Path

from git_cuttle.metadata_manager import RepoMetadata, WorkspaceMetadata
from git_cuttle.remote_status import (
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
