import subprocess
from pathlib import Path

import pytest

from git_cuttle.absorb import absorb_octopus_workspace
from git_cuttle.errors import AppError
from git_cuttle.metadata_manager import WorkspaceMetadata


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


def _workspace_metadata(*, branch: str, worktree: Path) -> WorkspaceMetadata:
    return WorkspaceMetadata(
        branch=branch,
        worktree_path=worktree,
        tracked_remote=None,
        kind="octopus",
        base_ref="main",
        octopus_parents=("main", "release"),
        created_at="2026-03-02T00:00:00Z",
        updated_at="2026-03-02T00:00:00Z",
    )


def _setup_octopus_repo(tmp_path: Path) -> tuple[Path, WorkspaceMetadata]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)

    _git(cwd=repo, args=["checkout", "-b", "release"])
    (repo / "release.txt").write_text("release v1\n")
    _git(cwd=repo, args=["add", "release.txt"])
    _git(cwd=repo, args=["commit", "-m", "release v1"])

    _git(cwd=repo, args=["checkout", "main"])
    (repo / "main.txt").write_text("main v1\n")
    _git(cwd=repo, args=["add", "main.txt"])
    _git(cwd=repo, args=["commit", "-m", "main v1"])

    _git(cwd=repo, args=["checkout", "-b", "integration/main-release", "main"])
    _git(cwd=repo, args=["merge", "--no-ff", "-m", "Create octopus workspace", "release"])
    return repo, _workspace_metadata(branch="integration/main-release", worktree=repo)


@pytest.mark.integration
def test_absorb_explicit_target_moves_post_merge_commits_to_target_parent(tmp_path: Path) -> None:
    repo, workspace = _setup_octopus_repo(tmp_path)

    (repo / "release-only-1.txt").write_text("r1\n")
    _git(cwd=repo, args=["add", "release-only-1.txt"])
    _git(cwd=repo, args=["commit", "-m", "release-only-1"])

    (repo / "release-only-2.txt").write_text("r2\n")
    _git(cwd=repo, args=["add", "release-only-2.txt"])
    _git(cwd=repo, args=["commit", "-m", "release-only-2"])

    old_head = _git(cwd=repo, args=["rev-parse", "--verify", "integration/main-release"]).stdout.strip()
    merge_commit = _git(cwd=repo, args=["rev-parse", "--verify", "integration/main-release~2"]).stdout.strip()

    result = absorb_octopus_workspace(
        repo_root=repo,
        workspace=workspace,
        target_parent="release",
    )

    new_head = _git(cwd=repo, args=["rev-parse", "--verify", "integration/main-release"]).stdout.strip()
    assert old_head != new_head
    assert new_head == merge_commit
    assert result.changed
    assert [entry.target_parent for entry in result.absorbed_commits] == ["release", "release"]

    release_log = _git(
        cwd=repo,
        args=["log", "--format=%s", "-n", "2", "release"],
    ).stdout.splitlines()
    assert release_log == ["release-only-2", "release-only-1"]


@pytest.mark.integration
def test_absorb_interactive_mode_uses_selected_parent(tmp_path: Path) -> None:
    repo, workspace = _setup_octopus_repo(tmp_path)

    (repo / "picked-main.txt").write_text("m\n")
    _git(cwd=repo, args=["add", "picked-main.txt"])
    _git(cwd=repo, args=["commit", "-m", "picked-main"])

    selections: list[tuple[str, tuple[str, ...]]] = []

    def choose_target(commit: str, parents: tuple[str, ...]) -> str:
        selections.append((commit, parents))
        return "main"

    result = absorb_octopus_workspace(
        repo_root=repo,
        workspace=workspace,
        interactive=True,
        choose_target=choose_target,
    )

    assert len(selections) == 1
    assert selections[0][1] == ("main", "release")
    assert len(result.absorbed_commits) == 1
    assert result.absorbed_commits[0].target_parent == "main"

    main_log = _git(cwd=repo, args=["log", "--format=%s", "-n", "1", "main"]).stdout.strip()
    assert main_log == "picked-main"


@pytest.mark.integration
def test_absorb_heuristic_mode_fails_when_target_is_ambiguous(tmp_path: Path) -> None:
    repo, workspace = _setup_octopus_repo(tmp_path)

    (repo / "README.md").write_text("ambiguous\n")
    _git(cwd=repo, args=["add", "README.md"])
    _git(cwd=repo, args=["commit", "-m", "touch shared file"])

    with pytest.raises(AppError) as exc_info:
        absorb_octopus_workspace(repo_root=repo, workspace=workspace)

    assert exc_info.value.code == "absorb-target-uncertain"
