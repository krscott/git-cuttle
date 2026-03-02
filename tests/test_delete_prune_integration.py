import subprocess
from pathlib import Path

import pytest

from git_cuttle.delete import current_branch, delete_block_reason
from git_cuttle.prune import prune_candidate_for_branch, prune_reason


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
