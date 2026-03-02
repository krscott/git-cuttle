import subprocess
from pathlib import Path

import pytest

from git_cuttle.errors import AppError
from git_cuttle.delete import current_branch, delete_block_reason
from git_cuttle.delete import delete_workspace
from git_cuttle.metadata_manager import MetadataManager
from git_cuttle.new import create_standard_workspace
from git_cuttle.prune import prune_candidate_for_branch, prune_reason, prune_workspaces


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


@pytest.mark.integration
def test_delete_blocks_current_workspace_without_force(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    _git(cwd=repo, args=["checkout", "-b", "feature/current"])

    active_branch = current_branch(cwd=repo)

    assert active_branch == "feature/current"
    assert (
        delete_block_reason(current=active_branch, target="feature/current", force=False)
        == "current-workspace"
    )
    assert delete_block_reason(current=active_branch, target="feature/current", force=True) is None


@pytest.mark.integration
def test_prune_marks_missing_local_branch_as_candidate(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    _git(cwd=repo, args=["checkout", "-b", "feature/gone"])
    _git(cwd=repo, args=["checkout", "main"])
    _git(cwd=repo, args=["branch", "-D", "feature/gone"])

    candidate = prune_candidate_for_branch(
        repo_root=repo,
        branch="feature/gone",
        pr_status="unknown",
    )

    assert not candidate.local_branch_exists
    assert prune_reason(candidate) == "missing-local-branch"


@pytest.mark.integration
def test_prune_does_not_remove_branch_for_unknown_pr_state(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    _git(cwd=repo, args=["checkout", "-b", "feature/unknown-pr"])

    candidate = prune_candidate_for_branch(
        repo_root=repo,
        branch="feature/unknown-pr",
        pr_status="unknown",
    )

    assert candidate.local_branch_exists
    assert prune_reason(candidate) is None


@pytest.mark.integration
def test_delete_requires_tracked_workspace(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)

    metadata_path = tmp_path / "workspaces.json"
    manager = MetadataManager(path=metadata_path)
    manager.ensure_repo_tracked(cwd=repo)

    with pytest.raises(AppError) as exc_info:
        delete_workspace(
            cwd=repo,
            branch="feature/missing",
            metadata_manager=manager,
        )

    assert exc_info.value.code == "workspace-not-tracked"


@pytest.mark.integration
def test_delete_dry_run_json_outputs_plan_without_changes(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)

    metadata_path = tmp_path / "workspaces.json"
    manager = MetadataManager(path=metadata_path)
    destination = create_standard_workspace(
        cwd=repo,
        branch="feature/delete-dry-run",
        base_ref="main",
        metadata_manager=manager,
    )

    rendered = delete_workspace(
        cwd=repo,
        branch="feature/delete-dry-run",
        metadata_manager=manager,
        dry_run=True,
        json_output=True,
    )

    assert rendered is not None
    assert '"command": "delete"' in rendered
    assert '"dry_run": true' in rendered
    assert '"target": "feature/delete-dry-run"' in rendered
    assert destination.exists()
    assert "feature/delete-dry-run" in next(iter(manager.read().repos.values())).workspaces


@pytest.mark.integration
def test_delete_blocks_dirty_workspace_without_force(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)

    metadata_path = tmp_path / "workspaces.json"
    manager = MetadataManager(path=metadata_path)
    destination = create_standard_workspace(
        cwd=repo,
        branch="feature/delete-dirty",
        base_ref="main",
        metadata_manager=manager,
    )
    (destination / "dirty.txt").write_text("dirty\n")

    with pytest.raises(AppError) as exc_info:
        delete_workspace(
            cwd=repo,
            branch="feature/delete-dirty",
            metadata_manager=manager,
        )

    assert exc_info.value.code == "workspace-dirty"


@pytest.mark.integration
def test_delete_force_removes_workspace_branch_and_metadata(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)

    metadata_path = tmp_path / "workspaces.json"
    manager = MetadataManager(path=metadata_path)
    destination = create_standard_workspace(
        cwd=repo,
        branch="feature/delete-force",
        base_ref="main",
        metadata_manager=manager,
    )
    (destination / "dirty.txt").write_text("dirty\n")

    delete_workspace(
        cwd=repo,
        branch="feature/delete-force",
        metadata_manager=manager,
        force=True,
    )

    branch_result = _git(
        cwd=repo,
        args=["show-ref", "--verify", "--quiet", "refs/heads/feature/delete-force"],
        check=False,
    )
    assert branch_result.returncode != 0
    assert not destination.exists()
    assert "feature/delete-force" not in next(iter(manager.read().repos.values())).workspaces


@pytest.mark.integration
def test_prune_dry_run_json_outputs_prune_plan_and_blocking_warning(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)

    metadata_path = tmp_path / "workspaces.json"
    manager = MetadataManager(path=metadata_path)

    clean_destination = create_standard_workspace(
        cwd=repo,
        branch="feature/prune-clean",
        base_ref="main",
        metadata_manager=manager,
    )
    dirty_destination = create_standard_workspace(
        cwd=repo,
        branch="feature/prune-dirty",
        base_ref="main",
        metadata_manager=manager,
    )
    (dirty_destination / "dirty.txt").write_text("dirty\n")

    rendered = prune_workspaces(
        cwd=repo,
        metadata_manager=manager,
        pr_status_by_branch={
            "feature/prune-clean": "merged",
            "feature/prune-dirty": "merged",
        },
        dry_run=True,
        json_output=True,
    )

    assert rendered is not None
    assert '"command": "prune"' in rendered
    assert '"op": "delete-branch"' in rendered
    assert '"target": "feature/prune-clean"' in rendered
    assert '"warnings": [' in rendered
    assert "feature/prune-dirty" in rendered
    assert clean_destination.exists()
    assert dirty_destination.exists()


@pytest.mark.integration
def test_prune_skips_current_workspace_without_force(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)

    metadata_path = tmp_path / "workspaces.json"
    manager = MetadataManager(path=metadata_path)
    destination = create_standard_workspace(
        cwd=repo,
        branch="feature/prune-current",
        base_ref="main",
        metadata_manager=manager,
    )

    prune_workspaces(
        cwd=destination,
        metadata_manager=manager,
        pr_status_by_branch={"feature/prune-current": "merged"},
    )

    branch_result = _git(
        cwd=repo,
        args=["show-ref", "--verify", "--quiet", "refs/heads/feature/prune-current"],
        check=False,
    )
    assert branch_result.returncode == 0
    assert destination.exists()
    assert "feature/prune-current" in next(iter(manager.read().repos.values())).workspaces


@pytest.mark.integration
def test_prune_force_removes_dirty_workspace_for_merged_pr(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)

    metadata_path = tmp_path / "workspaces.json"
    manager = MetadataManager(path=metadata_path)
    destination = create_standard_workspace(
        cwd=repo,
        branch="feature/prune-force",
        base_ref="main",
        metadata_manager=manager,
    )
    (destination / "dirty.txt").write_text("dirty\n")

    prune_workspaces(
        cwd=repo,
        metadata_manager=manager,
        pr_status_by_branch={"feature/prune-force": "merged"},
        force=True,
    )

    branch_result = _git(
        cwd=repo,
        args=["show-ref", "--verify", "--quiet", "refs/heads/feature/prune-force"],
        check=False,
    )
    assert branch_result.returncode != 0
    assert not destination.exists()
    assert "feature/prune-force" not in next(iter(manager.read().repos.values())).workspaces
