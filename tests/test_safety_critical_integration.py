import subprocess
from pathlib import Path

import pytest

from git_cuttle.delete import current_branch, delete_block_reason
from git_cuttle.git_ops import (
    add_worktree,
    backup_ref_for_branch,
    create_backup_refs_for_branches,
    remove_backup_refs,
    remove_worktree,
    restore_branch_from_backup_ref,
    set_branch_head,
)
from git_cuttle.metadata_manager import MetadataManager, WorkspacesMetadata, WorkspaceMetadata
from git_cuttle.remote_status import remote_ahead_behind_for_workspace
from git_cuttle.transaction import Transaction, TransactionExecutionError, TransactionRollbackError, TransactionStep


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
    (path / "README.md").write_text("repo\n")
    _git(cwd=path, args=["add", "README.md"])
    _git(cwd=path, args=["commit", "-m", "init"])


def _head_oid(*, repo: Path, ref: str) -> str:
    return _git(cwd=repo, args=["rev-parse", "--verify", ref]).stdout.strip()


@pytest.mark.integration
def test_transaction_rolls_back_mutations_on_failure(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    _git(cwd=repo, args=["checkout", "-b", "feature/demo"])
    _git(cwd=repo, args=["checkout", "main"])
    (repo / "main.txt").write_text("main\n")
    _git(cwd=repo, args=["add", "main.txt"])
    _git(cwd=repo, args=["commit", "-m", "main change"])

    original_feature_oid = _head_oid(repo=repo, ref="refs/heads/feature/demo")
    updated_feature_oid = _head_oid(repo=repo, ref="refs/heads/main")

    metadata_path = tmp_path / "workspaces.json"
    metadata_manager = MetadataManager(path=metadata_path)
    original_metadata = WorkspacesMetadata(version=1, repos={})
    metadata_manager.write(original_metadata)

    worktree_path = tmp_path / "feature-demo-wt"
    txn_id = "txn-safety-rollback"
    transaction = Transaction(txn_id=txn_id)

    transaction.add_step(
        TransactionStep(
            name="backup-refs",
            apply=lambda: create_backup_refs_for_branches(
                txn_id=txn_id,
                branches=["feature/demo"],
                cwd=repo,
            ),
            rollback=lambda: remove_backup_refs(txn_id=txn_id, cwd=repo),
        )
    )
    transaction.add_step(
        TransactionStep(
            name="update-branch-ref",
            apply=lambda: set_branch_head(
                branch="feature/demo",
                oid=updated_feature_oid,
                cwd=repo,
            ),
            rollback=lambda: restore_branch_from_backup_ref(
                txn_id=txn_id,
                branch="feature/demo",
                cwd=repo,
            ),
        )
    )
    transaction.add_step(
        TransactionStep(
            name="create-worktree",
            apply=lambda: add_worktree(branch="feature/demo", path=worktree_path, cwd=repo),
            rollback=lambda: remove_worktree(path=worktree_path, cwd=repo, force=True),
        )
    )
    transaction.add_step(
        TransactionStep(
            name="write-metadata",
            apply=lambda: metadata_manager.ensure_repo_tracked(
                cwd=repo,
                now=lambda: "2026-03-01T00:00:00Z",
            ),
            rollback=lambda: metadata_manager.write(original_metadata),
        )
    )
    transaction.add_step(
        TransactionStep(
            name="fail-after-mutations",
            apply=lambda: (_ for _ in ()).throw(RuntimeError("simulated failure")),
            rollback=lambda: None,
        )
    )

    with pytest.raises(TransactionExecutionError, match="fail-after-mutations"):
        transaction.run()

    assert _head_oid(repo=repo, ref="refs/heads/feature/demo") == original_feature_oid
    assert not worktree_path.exists()
    assert metadata_manager.read() == original_metadata

    backup_ref_result = _git(
        cwd=repo,
        args=["rev-parse", "--verify", backup_ref_for_branch(txn_id=txn_id, branch="feature/demo")],
        check=False,
    )
    assert backup_ref_result.returncode != 0


@pytest.mark.integration
def test_transaction_rollback_failure_reports_partial_state(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)

    transaction = Transaction(txn_id="txn-safety-partial")

    transaction.add_step(
        TransactionStep(
            name="apply-file-change",
            apply=lambda: (repo / "feature.txt").write_text("feature\n"),
            rollback=lambda: (_ for _ in ()).throw(RuntimeError("cleanup failed")),
            recovery_commands=("rm -f feature.txt",),
        )
    )
    transaction.add_step(
        TransactionStep(
            name="fail-update",
            apply=lambda: (_ for _ in ()).throw(RuntimeError("update failed")),
            rollback=lambda: None,
        )
    )

    with pytest.raises(TransactionRollbackError, match="rollback was partial") as exc_info:
        transaction.run()

    assert exc_info.value.recovery_commands() == ("rm -f feature.txt",)
    partial_state = exc_info.value.format_partial_state()
    assert "transaction id: txn-safety-partial" in partial_state
    assert "failed step: fail-update" in partial_state
    assert "- apply-file-change: cleanup failed" in partial_state
    assert "- rm -f feature.txt" in partial_state


@pytest.mark.integration
def test_remote_status_no_upstream_reports_unknown(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)

    workspace = WorkspaceMetadata(
        branch="main",
        worktree_path=repo,
        tracked_remote=None,
        kind="standard",
        base_ref="main",
        octopus_parents=(),
        created_at="2026-03-02T00:00:00Z",
        updated_at="2026-03-02T00:00:00Z",
    )

    status = remote_ahead_behind_for_workspace(
        repo_root=repo,
        workspace=workspace,
        default_remote=None,
    )

    assert status.upstream_ref is None
    assert status.ahead is None
    assert status.behind is None
    assert not status.known


@pytest.mark.integration
def test_delete_force_override_allows_current_workspace(tmp_path: Path) -> None:
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
