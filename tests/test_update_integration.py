import subprocess
from pathlib import Path

import pytest

from git_cuttle.errors import AppError
from git_cuttle.metadata_manager import WorkspaceMetadata
from git_cuttle.update import update_non_octopus_workspace, update_octopus_workspace


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


@pytest.mark.integration
def test_update_octopus_rebuilds_from_updated_parents_and_replays_post_merge_commits(
    tmp_path: Path,
) -> None:
    bare_remote, local = _clone_local_remote(tmp_path=tmp_path)

    _git(cwd=local, args=["checkout", "-b", "release"])
    (local / "release.txt").write_text("release v1\n")
    _git(cwd=local, args=["add", "release.txt"])
    _git(cwd=local, args=["commit", "-m", "release v1"])
    _git(cwd=local, args=["push", "-u", "origin", "release"])

    _git(cwd=local, args=["checkout", "main"])
    _git(cwd=local, args=["checkout", "-b", "integration/main-release", "main"])
    _git(cwd=local, args=["merge", "--no-ff", "-m", "Create octopus workspace", "release"])
    (local / "post-merge.txt").write_text("local post merge\n")
    _git(cwd=local, args=["add", "post-merge.txt"])
    _git(cwd=local, args=["commit", "-m", "post merge commit"])

    upstream_writer = tmp_path / "upstream-writer"
    _git(cwd=tmp_path, args=["clone", str(bare_remote), str(upstream_writer)])
    _git(cwd=upstream_writer, args=["config", "user.name", "Test User"])
    _git(cwd=upstream_writer, args=["config", "user.email", "test@example.com"])

    _git(cwd=upstream_writer, args=["checkout", "main"])
    (upstream_writer / "main.txt").write_text("main v2\n")
    _git(cwd=upstream_writer, args=["add", "main.txt"])
    _git(cwd=upstream_writer, args=["commit", "-m", "main v2"])
    _git(cwd=upstream_writer, args=["push", "origin", "main"])

    _git(cwd=upstream_writer, args=["checkout", "release"])
    (upstream_writer / "release.txt").write_text("release v2\n")
    _git(cwd=upstream_writer, args=["add", "release.txt"])
    _git(cwd=upstream_writer, args=["commit", "-m", "release v2"])
    _git(cwd=upstream_writer, args=["push", "origin", "release"])

    workspace = WorkspaceMetadata(
        branch="integration/main-release",
        worktree_path=local,
        tracked_remote="origin",
        kind="octopus",
        base_ref="main",
        octopus_parents=("main", "release"),
        created_at="2026-03-02T00:00:00Z",
        updated_at="2026-03-02T00:00:00Z",
    )

    result = update_octopus_workspace(
        repo_root=local,
        workspace=workspace,
        default_remote="origin",
    )

    rebuilt_merge_commit = _git(
        cwd=local,
        args=["rev-parse", "--verify", "integration/main-release^"],
    ).stdout.strip()
    rebuilt_merge_parents = _git(
        cwd=local,
        args=["show", "-s", "--format=%P", rebuilt_merge_commit],
    ).stdout.strip().split()
    expected_parents = [
        _git(cwd=local, args=["rev-parse", "--verify", "origin/main"]).stdout.strip(),
        _git(cwd=local, args=["rev-parse", "--verify", "origin/release"]).stdout.strip(),
    ]

    assert rebuilt_merge_parents == expected_parents
    assert (local / "post-merge.txt").read_text() == "local post merge\n"
    assert result.changed
    assert result.parent_refs == ("origin/main", "origin/release")
    assert len(result.replayed_commits) == 1


@pytest.mark.integration
def test_update_octopus_prefers_remote_parent_when_local_parent_is_ambiguous(tmp_path: Path) -> None:
    bare_remote, local = _clone_local_remote(tmp_path=tmp_path)

    _git(cwd=local, args=["checkout", "-b", "release"])
    (local / "release.txt").write_text("release local v1\n")
    _git(cwd=local, args=["add", "release.txt"])
    _git(cwd=local, args=["commit", "-m", "release local v1"])
    _git(cwd=local, args=["push", "-u", "origin", "release"])

    _git(cwd=local, args=["checkout", "main"])
    _git(cwd=local, args=["checkout", "-b", "integration/main-release", "main"])
    _git(cwd=local, args=["merge", "--no-ff", "-m", "Create octopus workspace", "release"])

    upstream_writer = tmp_path / "upstream-writer"
    _git(cwd=tmp_path, args=["clone", str(bare_remote), str(upstream_writer)])
    _git(cwd=upstream_writer, args=["config", "user.name", "Test User"])
    _git(cwd=upstream_writer, args=["config", "user.email", "test@example.com"])
    _git(cwd=upstream_writer, args=["checkout", "release"])
    (upstream_writer / "release.txt").write_text("release remote v2\n")
    _git(cwd=upstream_writer, args=["add", "release.txt"])
    _git(cwd=upstream_writer, args=["commit", "-m", "release remote v2"])
    _git(cwd=upstream_writer, args=["push", "origin", "release"])

    _git(cwd=local, args=["checkout", "release"])
    (local / "release-local-only.txt").write_text("local only\n")
    _git(cwd=local, args=["add", "release-local-only.txt"])
    _git(cwd=local, args=["commit", "-m", "release local only"])

    local_release_head = _git(cwd=local, args=["rev-parse", "--verify", "release"]).stdout.strip()

    workspace = WorkspaceMetadata(
        branch="integration/main-release",
        worktree_path=local,
        tracked_remote="origin",
        kind="octopus",
        base_ref="main",
        octopus_parents=("main", "release"),
        created_at="2026-03-02T00:00:00Z",
        updated_at="2026-03-02T00:00:00Z",
    )

    result = update_octopus_workspace(
        repo_root=local,
        workspace=workspace,
        default_remote="origin",
    )

    remote_release_head = _git(cwd=local, args=["rev-parse", "--verify", "origin/release"]).stdout.strip()
    assert local_release_head != remote_release_head
    assert result.parent_refs == ("origin/main", "origin/release")

    rebuilt_parent_commit = _git(
        cwd=local,
        args=["rev-parse", "--verify", "integration/main-release"],
    ).stdout.strip()
    rebuilt_merge_parents = _git(
        cwd=local,
        args=["show", "-s", "--format=%P", rebuilt_parent_commit],
    ).stdout.strip().split()
    assert rebuilt_merge_parents[1] == remote_release_head
