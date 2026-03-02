import pathlib
import subprocess

import pytest

from git_cuttle.git_ops import (
    backup_ref_for_branch,
    create_backup_refs_for_branches,
    in_progress_operation,
    remove_backup_refs,
)


def _init_repo(path: pathlib.Path) -> None:
    subprocess.run(["git", "init", "-b", "main"], check=True, cwd=path)
    subprocess.run(["git", "config", "user.name", "Test User"], check=True, cwd=path)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        check=True,
        cwd=path,
    )
    (path / "README.md").write_text("repo\n")
    subprocess.run(["git", "add", "README.md"], check=True, cwd=path)
    subprocess.run(["git", "commit", "-m", "init"], check=True, cwd=path)


def test_in_progress_operation_returns_none_when_repo_is_clean(
    tmp_path: pathlib.Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)

    assert in_progress_operation(repo) is None


def test_in_progress_operation_detects_git_state_marker(tmp_path: pathlib.Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)

    git_dir_result = subprocess.run(
        ["git", "rev-parse", "--git-dir"],
        capture_output=True,
        text=True,
        check=True,
        cwd=repo,
    )
    git_dir = pathlib.Path(git_dir_result.stdout.strip())
    if not git_dir.is_absolute():
        git_dir = (repo / git_dir).resolve(strict=False)

    (git_dir / "MERGE_HEAD").write_text("abc123\n")

    assert in_progress_operation(repo) == "MERGE_HEAD"


def test_create_backup_refs_for_branches_creates_snapshot_refs(
    tmp_path: pathlib.Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    subprocess.run(["git", "checkout", "-b", "feature/one"], check=True, cwd=repo)

    created = create_backup_refs_for_branches(
        txn_id="txn-123",
        branches=["main", "feature/one"],
        cwd=repo,
    )

    assert created == {
        "main": "refs/gitcuttle/txn/txn-123/heads/main",
        "feature/one": "refs/gitcuttle/txn/txn-123/heads/feature/one",
    }

    for branch in ("main", "feature/one"):
        head_oid = subprocess.run(
            ["git", "rev-parse", "--verify", f"refs/heads/{branch}"],
            capture_output=True,
            text=True,
            check=True,
            cwd=repo,
        ).stdout.strip()
        backup_oid = subprocess.run(
            [
                "git",
                "rev-parse",
                "--verify",
                backup_ref_for_branch(txn_id="txn-123", branch=branch),
            ],
            capture_output=True,
            text=True,
            check=True,
            cwd=repo,
        ).stdout.strip()
        assert backup_oid == head_oid


def test_create_backup_refs_for_branches_fails_for_missing_branch(
    tmp_path: pathlib.Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)

    with pytest.raises(RuntimeError, match="branch does not exist: missing"):
        create_backup_refs_for_branches(
            txn_id="txn-123",
            branches=["missing"],
            cwd=repo,
        )


def test_remove_backup_refs_removes_only_transaction_refs(
    tmp_path: pathlib.Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)

    create_backup_refs_for_branches(txn_id="txn-keep", branches=["main"], cwd=repo)
    create_backup_refs_for_branches(txn_id="txn-drop", branches=["main"], cwd=repo)

    remove_backup_refs(txn_id="txn-drop", cwd=repo)

    dropped = subprocess.run(
        [
            "git",
            "rev-parse",
            "--verify",
            backup_ref_for_branch(txn_id="txn-drop", branch="main"),
        ],
        capture_output=True,
        text=True,
        check=False,
        cwd=repo,
    )
    assert dropped.returncode != 0

    kept = subprocess.run(
        [
            "git",
            "rev-parse",
            "--verify",
            backup_ref_for_branch(txn_id="txn-keep", branch="main"),
        ],
        capture_output=True,
        text=True,
        check=True,
        cwd=repo,
    )
    assert kept.returncode == 0
