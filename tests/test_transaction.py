import pytest
import subprocess
from pathlib import Path

from git_cuttle.git_ops import (
    add_worktree,
    backup_ref_for_branch,
    create_backup_refs_for_branches,
    remove_backup_refs,
    remove_worktree,
    restore_branch_from_backup_ref,
    set_branch_head,
)
from git_cuttle.metadata_manager import MetadataManager, WorkspacesMetadata
from git_cuttle.transaction import (
    RollbackFailure,
    Transaction,
    TransactionExecutionError,
    TransactionRollbackError,
    TransactionStep,
    run_transaction,
)


def test_transaction_runs_steps_in_order() -> None:
    calls: list[str] = []
    transaction = Transaction(txn_id="txn-1")

    transaction.add_step(
        TransactionStep(
            name="create-branch",
            apply=lambda: calls.append("apply:create-branch"),
            rollback=lambda: calls.append("rollback:create-branch"),
        )
    )
    transaction.add_step(
        TransactionStep(
            name="create-worktree",
            apply=lambda: calls.append("apply:create-worktree"),
            rollback=lambda: calls.append("rollback:create-worktree"),
        )
    )

    transaction.run()

    assert calls == ["apply:create-branch", "apply:create-worktree"]


def test_transaction_rolls_back_completed_steps_on_failure() -> None:
    calls: list[str] = []
    transaction = Transaction(txn_id="txn-2")

    transaction.add_step(
        TransactionStep(
            name="create-branch",
            apply=lambda: calls.append("apply:create-branch"),
            rollback=lambda: calls.append("rollback:create-branch"),
        )
    )

    def fail_worktree() -> None:
        calls.append("apply:create-worktree")
        raise RuntimeError("worktree add failed")

    transaction.add_step(
        TransactionStep(
            name="create-worktree",
            apply=fail_worktree,
            rollback=lambda: calls.append("rollback:create-worktree"),
        )
    )

    with pytest.raises(TransactionExecutionError, match="create-worktree") as exc_info:
        transaction.run()

    assert calls == [
        "apply:create-branch",
        "apply:create-worktree",
        "rollback:create-branch",
    ]
    assert exc_info.value.rolled_back_steps == ("create-branch",)


def test_transaction_raises_rollback_error_when_rollback_fails() -> None:
    calls: list[str] = []
    transaction = Transaction(txn_id="txn-3")

    def create_branch() -> None:
        calls.append("apply:create-branch")

    def rollback_branch() -> None:
        calls.append("rollback:create-branch")
        raise RuntimeError("branch delete failed")

    def fail_worktree() -> None:
        calls.append("apply:create-worktree")
        raise RuntimeError("worktree add failed")

    transaction.add_step(
        TransactionStep(
            name="create-branch",
            apply=create_branch,
            rollback=rollback_branch,
            recovery_commands=(
                "git branch -f feature/demo refs/gitcuttle/txn/txn-3/heads/feature/demo",
                "git worktree remove --force /tmp/feature-demo-wt",
            ),
        )
    )
    transaction.add_step(
        TransactionStep(
            name="create-worktree",
            apply=fail_worktree,
            rollback=lambda: calls.append("rollback:create-worktree"),
        )
    )

    with pytest.raises(TransactionRollbackError, match="rollback was partial") as exc_info:
        transaction.run()

    assert calls == [
        "apply:create-branch",
        "apply:create-worktree",
        "rollback:create-branch",
    ]
    assert len(exc_info.value.rollback_failures) == 1
    assert exc_info.value.rollback_failures[0].step_name == "create-branch"
    assert exc_info.value.rollback_failures[0].recovery_commands == (
        "git branch -f feature/demo refs/gitcuttle/txn/txn-3/heads/feature/demo",
        "git worktree remove --force /tmp/feature-demo-wt",
    )
    assert exc_info.value.rolled_back_steps == ()

    assert exc_info.value.recovery_commands() == (
        "git branch -f feature/demo refs/gitcuttle/txn/txn-3/heads/feature/demo",
        "git worktree remove --force /tmp/feature-demo-wt",
    )
    assert exc_info.value.format_partial_state() == (
        "transaction id: txn-3\n"
        "failed step: create-worktree\n"
        "operation error: worktree add failed\n"
        "rolled back steps: (none)\n"
        "rollback failures:\n"
        "- create-branch: branch delete failed\n"
        "deterministic recovery commands:\n"
        "- git branch -f feature/demo refs/gitcuttle/txn/txn-3/heads/feature/demo\n"
        "- git worktree remove --force /tmp/feature-demo-wt"
    )


def test_rollback_error_deduplicates_recovery_commands_in_order() -> None:
    error = TransactionRollbackError(
        txn_id="txn-dedupe",
        failed_step_name="apply-merge",
        cause=RuntimeError("merge failed"),
        rollback_failures=(
            RollbackFailure(
                step_name="restore-ref",
                error=RuntimeError("restore failed"),
                recovery_commands=(
                    "git update-ref refs/heads/feature abc123",
                    "git worktree prune",
                ),
            ),
            RollbackFailure(
                step_name="remove-worktree",
                error=RuntimeError("remove failed"),
                recovery_commands=(
                    "git worktree prune",
                    "git worktree remove --force /tmp/feature",
                ),
            ),
        ),
        rolled_back_steps=("write-metadata",),
    )

    assert error.recovery_commands() == (
        "git update-ref refs/heads/feature abc123",
        "git worktree prune",
        "git worktree remove --force /tmp/feature",
    )


def test_run_transaction_returns_effective_transaction_id() -> None:
    txn_id = run_transaction(
        txn_id="txn-4",
        steps=(
            TransactionStep(
                name="no-op",
                apply=lambda: None,
                rollback=lambda: None,
            ),
        ),
    )

    assert txn_id == "txn-4"


def _init_repo(path: Path) -> None:
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


def _head_oid(*, repo: Path, ref: str) -> str:
    return subprocess.run(
        ["git", "rev-parse", "--verify", ref],
        capture_output=True,
        text=True,
        check=True,
        cwd=repo,
    ).stdout.strip()


def test_transaction_rolls_back_refs_worktree_and_metadata_on_failure(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    subprocess.run(["git", "checkout", "-b", "feature/demo"], check=True, cwd=repo)
    subprocess.run(["git", "checkout", "main"], check=True, cwd=repo)
    (repo / "main.txt").write_text("main\n")
    subprocess.run(["git", "add", "main.txt"], check=True, cwd=repo)
    subprocess.run(["git", "commit", "-m", "main change"], check=True, cwd=repo)

    original_feature_oid = _head_oid(repo=repo, ref="refs/heads/feature/demo")
    updated_feature_oid = _head_oid(repo=repo, ref="refs/heads/main")

    metadata_path = tmp_path / "workspaces.json"
    metadata_manager = MetadataManager(path=metadata_path)
    original_metadata = WorkspacesMetadata(version=1, repos={})
    metadata_manager.write(original_metadata)

    worktree_path = tmp_path / "feature-demo-wt"
    txn_id = "txn-full-rollback"
    transaction = Transaction(txn_id=txn_id)

    def create_backup_refs() -> None:
        _ = create_backup_refs_for_branches(
            txn_id=txn_id,
            branches=["feature/demo"],
            cwd=repo,
        )

    transaction.add_step(
        TransactionStep(
            name="backup-refs",
            apply=create_backup_refs,
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
            apply=lambda: add_worktree(
                branch="feature/demo",
                path=worktree_path,
                cwd=repo,
            ),
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

    def fail_after_mutations() -> None:
        raise RuntimeError("simulated failure")

    transaction.add_step(
        TransactionStep(
            name="fail-after-mutations",
            apply=fail_after_mutations,
            rollback=lambda: None,
        )
    )

    with pytest.raises(TransactionExecutionError, match="fail-after-mutations"):
        transaction.run()

    assert _head_oid(repo=repo, ref="refs/heads/feature/demo") == original_feature_oid
    assert not worktree_path.exists()
    assert metadata_manager.read() == original_metadata

    backup_ref_result = subprocess.run(
        [
            "git",
            "rev-parse",
            "--verify",
            backup_ref_for_branch(txn_id=txn_id, branch="feature/demo"),
        ],
        capture_output=True,
        text=True,
        check=False,
        cwd=repo,
    )
    assert backup_ref_result.returncode != 0
