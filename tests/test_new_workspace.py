import subprocess
from pathlib import Path

import pytest

from git_cuttle.errors import AppError
from git_cuttle.metadata_manager import MetadataManager
from git_cuttle.new import create_octopus_workspace, create_standard_workspace, resolve_base_ref


def _git(*, cwd: Path, args: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        check=check,
        cwd=cwd,
    )


def _init_repo(path: Path) -> None:
    _git(cwd=path, args=["init", "-b", "main"])
    _git(cwd=path, args=["config", "user.name", "Test User"])
    _git(cwd=path, args=["config", "user.email", "test@example.com"])
    (path / "README.md").write_text("hello\n")
    _git(cwd=path, args=["add", "README.md"])
    _git(cwd=path, args=["commit", "-m", "init"])


@pytest.mark.integration
def test_resolve_base_ref_defaults_to_current_branch(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    _git(cwd=repo, args=["checkout", "-b", "feature/base"])

    resolved = resolve_base_ref(cwd=repo, base_ref=None)

    assert resolved == "feature/base"


@pytest.mark.integration
def test_create_standard_workspace_creates_branch_worktree_and_metadata(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    metadata_path = tmp_path / "workspaces.json"
    metadata_manager = MetadataManager(path=metadata_path)

    destination = create_standard_workspace(
        cwd=repo,
        branch="feature/new-workspace",
        base_ref="main",
        metadata_manager=metadata_manager,
    )

    assert destination.exists()
    assert destination.is_dir()

    branch_result = _git(cwd=repo, args=["rev-parse", "--verify", "feature/new-workspace"], check=False)
    assert branch_result.returncode == 0

    metadata = metadata_manager.read()
    assert len(metadata.repos) == 1
    tracked_repo = next(iter(metadata.repos.values()))
    assert "feature/new-workspace" in tracked_repo.workspaces
    workspace = tracked_repo.workspaces["feature/new-workspace"]
    assert workspace.kind == "standard"
    assert workspace.base_ref == "main"
    assert workspace.worktree_path == destination


@pytest.mark.integration
def test_create_standard_workspace_rejects_existing_branch(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    _git(cwd=repo, args=["checkout", "-b", "feature/existing"])
    _git(cwd=repo, args=["checkout", "main"])

    metadata_path = tmp_path / "workspaces.json"
    metadata_manager = MetadataManager(path=metadata_path)

    with pytest.raises(AppError) as exc_info:
        create_standard_workspace(
            cwd=repo,
            branch="feature/existing",
            base_ref="main",
            metadata_manager=metadata_manager,
        )

    assert exc_info.value.code == "branch-already-exists"
    assert exc_info.value.message == "target branch already exists"


@pytest.mark.integration
def test_create_octopus_workspace_creates_n_way_merge_and_tracks_parent_order(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)

    _git(cwd=repo, args=["checkout", "-b", "release"])
    (repo / "release.txt").write_text("release\n")
    _git(cwd=repo, args=["add", "release.txt"])
    _git(cwd=repo, args=["commit", "-m", "release"])

    _git(cwd=repo, args=["checkout", "main"])
    _git(cwd=repo, args=["checkout", "-b", "hotfix"])
    (repo / "hotfix.txt").write_text("hotfix\n")
    _git(cwd=repo, args=["add", "hotfix.txt"])
    _git(cwd=repo, args=["commit", "-m", "hotfix"])

    _git(cwd=repo, args=["checkout", "main"])
    metadata_path = tmp_path / "workspaces.json"
    metadata_manager = MetadataManager(path=metadata_path)

    destination = create_octopus_workspace(
        cwd=repo,
        branch="integration/main-release-hotfix",
        parent_refs=["main", "release", "hotfix"],
        metadata_manager=metadata_manager,
    )

    assert destination.exists()
    assert destination.is_dir()

    parent_commits = _git(
        cwd=repo,
        args=["show", "-s", "--format=%P", "integration/main-release-hotfix"],
    ).stdout.strip().split()
    expected_parents = [
        _git(cwd=repo, args=["rev-parse", "--verify", parent]).stdout.strip()
        for parent in ["main", "release", "hotfix"]
    ]
    assert parent_commits == expected_parents

    metadata = metadata_manager.read()
    tracked_repo = next(iter(metadata.repos.values()))
    workspace = tracked_repo.workspaces["integration/main-release-hotfix"]
    assert workspace.kind == "octopus"
    assert workspace.base_ref == "main"
    assert workspace.octopus_parents == ("main", "release", "hotfix")


@pytest.mark.integration
def test_create_octopus_workspace_requires_at_least_two_parent_refs(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)

    metadata_path = tmp_path / "workspaces.json"
    metadata_manager = MetadataManager(path=metadata_path)

    with pytest.raises(AppError) as exc_info:
        create_octopus_workspace(
            cwd=repo,
            branch="integration/main-only",
            parent_refs=["main"],
            metadata_manager=metadata_manager,
        )

    assert exc_info.value.code == "invalid-octopus-parents"


@pytest.mark.integration
def test_create_octopus_workspace_rejects_duplicate_parent_refs(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)

    _git(cwd=repo, args=["checkout", "-b", "release"])

    metadata_path = tmp_path / "workspaces.json"
    metadata_manager = MetadataManager(path=metadata_path)

    with pytest.raises(AppError) as exc_info:
        create_octopus_workspace(
            cwd=repo,
            branch="integration/main-release-main",
            parent_refs=["main", "release", "main"],
            metadata_manager=metadata_manager,
        )

    assert exc_info.value.code == "invalid-octopus-parents"
    assert exc_info.value.message == "octopus parent refs must be unique"
