import json
import os
import subprocess
from pathlib import Path

import pytest

from git_cuttle.metadata_manager import (
    MetadataManager,
    RepoMetadata,
    WorkspaceMetadata,
    WorkspacesMetadata,
)


def _git(
    *, cwd: Path, args: list[str], check: bool = True
) -> subprocess.CompletedProcess[str]:
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


def _canonical_git_dir(repo: Path) -> Path:
    git_dir = _git(cwd=repo, args=["rev-parse", "--git-dir"]).stdout.strip()
    candidate = Path(git_dir)
    if candidate.is_absolute():
        return candidate.resolve(strict=False)
    return (repo / candidate).resolve(strict=False)


def _write_repo_metadata(
    *,
    metadata_path: Path,
    repo: Path,
    default_remote: str | None,
    workspace: WorkspaceMetadata,
) -> None:
    manager = MetadataManager(path=metadata_path)
    canonical_git_dir = _canonical_git_dir(repo)
    repo_root = repo.resolve(strict=False)
    record = RepoMetadata(
        git_dir=canonical_git_dir,
        repo_root=repo_root,
        default_remote=default_remote,
        tracked_at="2026-03-02T00:00:00Z",
        updated_at="2026-03-02T00:00:00Z",
        workspaces={workspace.branch: workspace},
    )
    manager.write(
        WorkspacesMetadata(
            version=1,
            repos={str(canonical_git_dir): record},
        )
    )


def _run_update(*, cwd: Path, xdg_data_home: Path) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["XDG_DATA_HOME"] = str(xdg_data_home)
    return subprocess.run(
        ["gitcuttle", "update"],
        check=False,
        capture_output=True,
        text=True,
        cwd=cwd,
        env=env,
    )


@pytest.mark.integration
def test_cli_update_rebases_standard_workspace_onto_upstream(tmp_path: Path) -> None:
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
    upstream_head = _git(
        cwd=upstream_writer, args=["rev-parse", "--verify", "HEAD"]
    ).stdout.strip()

    (local / "local.txt").write_text("local c\n")
    _git(cwd=local, args=["add", "local.txt"])
    _git(cwd=local, args=["commit", "-m", "local c"])

    xdg_data_home = tmp_path / "xdg"
    metadata_path = xdg_data_home / "gitcuttle" / "workspaces.json"
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
    _write_repo_metadata(
        metadata_path=metadata_path,
        repo=local,
        default_remote="origin",
        workspace=workspace,
    )

    result = _run_update(cwd=local, xdg_data_home=xdg_data_home)

    assert result.returncode == 0
    assert (
        "updated standard workspace feature/update onto origin/feature/update"
        in result.stdout
    )
    rebased_parent = _git(
        cwd=local, args=["show", "-s", "--format=%P", "HEAD"]
    ).stdout.strip()
    assert rebased_parent == upstream_head


@pytest.mark.integration
def test_cli_update_errors_for_standard_workspace_without_upstream(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    _git(cwd=repo, args=["checkout", "-b", "feature/no-upstream"])

    xdg_data_home = tmp_path / "xdg"
    metadata_path = xdg_data_home / "gitcuttle" / "workspaces.json"
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
    _write_repo_metadata(
        metadata_path=metadata_path,
        repo=repo,
        default_remote=None,
        workspace=workspace,
    )

    result = _run_update(cwd=repo, xdg_data_home=xdg_data_home)

    assert result.returncode == 2
    assert (
        "error[no-upstream]: workspace has no upstream remote branch configured"
        in result.stderr
    )


@pytest.mark.integration
def test_cli_update_reports_rebase_conflict_recovery_guidance(tmp_path: Path) -> None:
    bare_remote, local = _clone_local_remote(tmp_path=tmp_path)

    _git(cwd=local, args=["checkout", "-b", "feature/conflict"])
    (local / "shared.txt").write_text("base line\n")
    _git(cwd=local, args=["add", "shared.txt"])
    _git(cwd=local, args=["commit", "-m", "add shared file"])
    _git(cwd=local, args=["push", "-u", "origin", "feature/conflict"])

    upstream_writer = tmp_path / "upstream-writer"
    _git(cwd=tmp_path, args=["clone", str(bare_remote), str(upstream_writer)])
    _git(cwd=upstream_writer, args=["config", "user.name", "Test User"])
    _git(cwd=upstream_writer, args=["config", "user.email", "test@example.com"])
    _git(cwd=upstream_writer, args=["checkout", "feature/conflict"])
    (upstream_writer / "shared.txt").write_text("upstream edit\n")
    _git(cwd=upstream_writer, args=["add", "shared.txt"])
    _git(cwd=upstream_writer, args=["commit", "-m", "upstream edit"])
    _git(cwd=upstream_writer, args=["push", "origin", "feature/conflict"])

    (local / "shared.txt").write_text("local edit\n")
    _git(cwd=local, args=["add", "shared.txt"])
    _git(cwd=local, args=["commit", "-m", "local edit"])

    xdg_data_home = tmp_path / "xdg"
    metadata_path = xdg_data_home / "gitcuttle" / "workspaces.json"
    workspace = WorkspaceMetadata(
        branch="feature/conflict",
        worktree_path=local,
        tracked_remote="origin",
        kind="standard",
        base_ref="main",
        octopus_parents=(),
        created_at="2026-03-02T00:00:00Z",
        updated_at="2026-03-02T00:00:00Z",
    )
    _write_repo_metadata(
        metadata_path=metadata_path,
        repo=local,
        default_remote="origin",
        workspace=workspace,
    )

    result = _run_update(cwd=local, xdg_data_home=xdg_data_home)

    assert result.returncode == 2
    assert "error[update-rebase-failed]: failed to rebase branch onto upstream" in result.stderr
    assert "hint: resolve conflicts, then run `git rebase --continue`" in result.stderr
    assert (
        "hint: or run `git rebase --abort` to restore a clean git state before retrying"
        in result.stderr
    )


@pytest.mark.integration
def test_cli_update_rebuilds_octopus_workspace_and_replays_commits(
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
    _git(
        cwd=local,
        args=["merge", "--no-ff", "-m", "Create octopus workspace", "release"],
    )
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

    _git(cwd=local, args=["checkout", "integration/main-release"])
    xdg_data_home = tmp_path / "xdg"
    metadata_path = xdg_data_home / "gitcuttle" / "workspaces.json"
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
    _write_repo_metadata(
        metadata_path=metadata_path,
        repo=local,
        default_remote="origin",
        workspace=workspace,
    )

    result = _run_update(cwd=local, xdg_data_home=xdg_data_home)

    assert result.returncode == 0
    assert "rebuilt octopus workspace integration/main-release" in result.stdout

    rebuilt_merge_commit = _git(
        cwd=local,
        args=["rev-parse", "--verify", "integration/main-release^"],
    ).stdout.strip()
    rebuilt_merge_parents = (
        _git(
            cwd=local,
            args=["show", "-s", "--format=%P", rebuilt_merge_commit],
        )
        .stdout.strip()
        .split()
    )
    expected_parents = [
        _git(cwd=local, args=["rev-parse", "--verify", "main"]).stdout.strip(),
        _git(cwd=local, args=["rev-parse", "--verify", "release"]).stdout.strip(),
    ]

    assert rebuilt_merge_parents == expected_parents
    assert (local / "post-merge.txt").read_text() == "local post merge\n"

    metadata_payload = json.loads(metadata_path.read_text())
    assert metadata_payload["version"] == 1
