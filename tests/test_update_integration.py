import subprocess
from pathlib import Path

import pytest

from git_cuttle.errors import AppError
from git_cuttle.metadata_manager import WorkspaceMetadata
from git_cuttle.update import update_non_octopus_workspace


def _git(*, cwd: Path, args: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        check=check,
        capture_output=True,
        text=True,
        cwd=cwd,
    )


def _init_repo(path: Path) -> None:
    _git(cwd=path, args=["init", "-b", "main"])
    _git(cwd=path, args=["config", "user.name", "Test User"])
    _git(cwd=path, args=["config", "user.email", "test@example.com"])
    (path / "README.md").write_text("hello\n")
    _git(cwd=path, args=["add", "README.md"])
    _git(cwd=path, args=["commit", "-m", "init"])


def _clone_local_remote(*, tmp_path: Path) -> tuple[Path, Path]:
    source = tmp_path / "source"
    source.mkdir()
    _init_repo(source)

    bare_remote = tmp_path / "remote.git"
    _git(cwd=source, args=["clone", "--bare", str(source), str(bare_remote)])

    local = tmp_path / "local"
    _git(cwd=tmp_path, args=["clone", str(bare_remote), str(local)])
    _git(cwd=local, args=["config", "user.name", "Test User"])
    _git(cwd=local, args=["config", "user.email", "test@example.com"])

    return bare_remote, local


@pytest.mark.integration
def test_update_non_octopus_rebases_local_commit_onto_upstream(tmp_path: Path) -> None:
    bare_remote, local = _clone_local_remote(tmp_path=tmp_path)

    _git(cwd=local, args=["checkout", "-b", "feature/update"])
    (local / "feature.txt").write_text("local a\n")
    _git(cwd=local, args=["add", "feature.txt"])
    _git(cwd=local, args=["commit", "-m", "local a"])
    _git(cwd=local, args=["push", "-u", "origin", "feature/update"])

    upstream_writer = tmp_path / "upstream-writer"
    _git(cwd=tmp_path, args=["clone", str(bare_remote), str(upstream_writer)])
    _git(cwd=upstream_writer, args=["config", "user.name", "Test User"])
    _git(cwd=upstream_writer, args=["config", "user.email", "test@example.com"])
    _git(cwd=upstream_writer, args=["checkout", "feature/update"])
    (upstream_writer / "upstream.txt").write_text("upstream b\n")
    _git(cwd=upstream_writer, args=["add", "upstream.txt"])
    _git(cwd=upstream_writer, args=["commit", "-m", "upstream b"])
    _git(cwd=upstream_writer, args=["push", "origin", "feature/update"])
    upstream_head = _git(cwd=upstream_writer, args=["rev-parse", "--verify", "HEAD"]).stdout.strip()

    (local / "local.txt").write_text("local c\n")
    _git(cwd=local, args=["add", "local.txt"])
    _git(cwd=local, args=["commit", "-m", "local c"])

    workspace = WorkspaceMetadata(
        branch="feature/update",
        worktree_path=local,
        tracked_remote="origin",
        kind="standard",
        base_ref="main",
        octopus_parents=(),
        created_at="2026-03-02T00:00:00Z",
        updated_at="2026-03-02T00:00:00Z",
    )

    result = update_non_octopus_workspace(
        repo_root=local,
        workspace=workspace,
        default_remote="origin",
    )

    rebased_parent = _git(cwd=local, args=["show", "-s", "--format=%P", "HEAD"]).stdout.strip()
    assert rebased_parent == upstream_head
    assert result.changed


@pytest.mark.integration
def test_update_non_octopus_fails_when_no_upstream_is_configured(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    _git(cwd=repo, args=["checkout", "-b", "feature/no-upstream"])

    workspace = WorkspaceMetadata(
        branch="feature/no-upstream",
        worktree_path=repo,
        tracked_remote=None,
        kind="standard",
        base_ref="main",
        octopus_parents=(),
        created_at="2026-03-02T00:00:00Z",
        updated_at="2026-03-02T00:00:00Z",
    )

    with pytest.raises(AppError) as exc_info:
        update_non_octopus_workspace(
            repo_root=repo,
            workspace=workspace,
            default_remote=None,
        )

    assert exc_info.value.code == "no-upstream"
