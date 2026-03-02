import pytest

from git_cuttle.transaction import (
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
    assert exc_info.value.rolled_back_steps == ()


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
