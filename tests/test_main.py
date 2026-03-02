import pytest

from git_cuttle.__main__ import main
from git_cuttle.cli import CliOpts
from git_cuttle.lib import Options
from git_cuttle.transaction import RollbackFailure, TransactionRollbackError


def test_main_surfaces_transaction_partial_state_recovery_contract(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        CliOpts,
        "parse_args",
        staticmethod(
            lambda: CliOpts(app_opts=Options(), command_name="list", verbose=False)
        ),
    )

    def fail_with_partial_rollback(*_: object, **__: object) -> None:
        raise TransactionRollbackError(
            txn_id="txn-cli-rollback",
            failed_step_name="write-metadata",
            cause=RuntimeError("operation exploded"),
            rollback_failures=(
                RollbackFailure(
                    step_name="restore-branch",
                    error=RuntimeError("branch restore failed"),
                    recovery_commands=(
                        "git branch -f feature/demo refs/gitcuttle/txn/txn-cli-rollback/heads/feature/demo",
                    ),
                ),
            ),
            rolled_back_steps=("backup-refs",),
        )

    monkeypatch.setattr("git_cuttle.__main__.run", fail_with_partial_rollback)

    with pytest.raises(SystemExit) as exit_info:
        main()

    assert exit_info.value.code == 2
    stderr = capsys.readouterr().err
    assert (
        "error[transaction-rollback-failed]: operation failed and automatic rollback was partial"
        in stderr
    )
    assert "details: transaction id: txn-cli-rollback" in stderr
    assert "failed step: write-metadata" in stderr
    assert "rollback failures:" in stderr
    assert "deterministic recovery commands:" in stderr
    assert (
        "git branch -f feature/demo refs/gitcuttle/txn/txn-cli-rollback/heads/feature/demo"
        in stderr
    )
