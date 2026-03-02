from collections.abc import Iterable
from pathlib import Path

from git_cuttle.errors import AppError
from git_cuttle.git_ops import (
    backup_ref_for_branch,
    create_backup_refs_for_branches,
    remove_backup_refs as remove_backup_refs,
    restore_branch_from_backup_ref,
    set_branch_head,
)
from git_cuttle.transaction import (
    Transaction,
    TransactionExecutionError,
    TransactionStep,
)


def run_command_transaction(
    *,
    transaction: Transaction,
    code: str,
    message: str,
) -> None:
    try:
        transaction.run()
    except TransactionExecutionError as error:
        if isinstance(error.cause, AppError):
            raise error.cause
        raise AppError(code=code, message=message, details=str(error.cause)) from error


def backup_refs_step(
    *,
    repo_root: Path,
    transaction: Transaction,
    branches: Iterable[str],
    backup_error_code: str,
    backup_error_message: str,
    rollback_error_code: str,
    rollback_error_message: str,
) -> TransactionStep:
    unique_branches = tuple(dict.fromkeys(branches))
    recovery_commands = tuple(
        _restore_backup_command(txn_id=transaction.txn_id, branch=branch)
        for branch in unique_branches
    )
    return TransactionStep(
        name="backup-refs",
        apply=lambda: _create_backup_refs(
            repo_root=repo_root,
            txn_id=transaction.txn_id,
            branches=unique_branches,
            error_code=backup_error_code,
            error_message=backup_error_message,
        ),
        rollback=lambda: _remove_backup_refs(
            repo_root=repo_root,
            txn_id=transaction.txn_id,
            error_code=rollback_error_code,
            error_message=rollback_error_message,
        ),
        recovery_commands=recovery_commands,
    )


def restore_branch_step(
    *,
    repo_root: Path,
    transaction: Transaction,
    branch: str,
    rollback_error_code: str,
    rollback_error_message: str,
    backup_oid: str | None = None,
) -> TransactionStep:
    recovery_commands = branch_restore_recovery_commands(
        transaction=transaction,
        branch=branch,
        backup_oid=backup_oid,
    )
    return TransactionStep(
        name=f"restore-branch:{branch}",
        apply=lambda: None,
        rollback=lambda: _restore_branch_from_backup_ref(
            repo_root=repo_root,
            txn_id=transaction.txn_id,
            branch=branch,
            backup_oid=backup_oid,
            error_code=rollback_error_code,
            error_message=rollback_error_message,
        ),
        recovery_commands=recovery_commands,
    )


def branch_restore_recovery_commands(
    *,
    transaction: Transaction,
    branch: str,
    backup_oid: str | None = None,
) -> tuple[str, ...]:
    if backup_oid is not None:
        return (f"git update-ref refs/heads/{branch} {backup_oid}",)

    backup_ref = backup_ref_for_branch(txn_id=transaction.txn_id, branch=branch)
    return (f"git update-ref refs/heads/{branch} {backup_ref}",)


def cleanup_backup_refs_step(
    *,
    repo_root: Path,
    transaction: Transaction,
    branches: Iterable[str],
    cleanup_error_code: str,
    cleanup_error_message: str,
) -> TransactionStep:
    unique_branches = tuple(dict.fromkeys(branches))
    return TransactionStep(
        name="cleanup-backup-refs",
        apply=lambda: _remove_backup_refs(
            repo_root=repo_root,
            txn_id=transaction.txn_id,
            error_code=cleanup_error_code,
            error_message=cleanup_error_message,
        ),
        rollback=lambda: None,
        recovery_commands=tuple(
            _delete_backup_ref_command(txn_id=transaction.txn_id, branch=branch)
            for branch in unique_branches
        ),
    )


def cleanup_backup_refs_post_commit(
    *,
    repo_root: Path,
    transaction: Transaction,
    branches: Iterable[str],
    cleanup_error_code: str,
    cleanup_error_message: str,
) -> None:
    unique_branches = tuple(dict.fromkeys(branches))
    if not unique_branches:
        return

    try:
        _remove_backup_refs(
            repo_root=repo_root,
            txn_id=transaction.txn_id,
            error_code=cleanup_error_code,
            error_message=cleanup_error_message,
        )
    except AppError as error:
        recovery_commands = tuple(
            _delete_backup_ref_command(txn_id=transaction.txn_id, branch=branch)
            for branch in unique_branches
        )
        raise AppError(
            code=error.code,
            message=error.message,
            details=error.details,
            guidance=tuple(f"run `{command}`" for command in recovery_commands),
        ) from error


def rollback_restore_branch(
    *,
    repo_root: Path,
    transaction: Transaction,
    branch: str,
    backup_oid: str | None = None,
    error_code: str,
    message: str,
) -> None:
    _restore_branch_from_backup_ref(
        repo_root=repo_root,
        txn_id=transaction.txn_id,
        branch=branch,
        backup_oid=backup_oid,
        error_code=error_code,
        error_message=message,
    )


def _create_backup_refs(
    *,
    repo_root: Path,
    txn_id: str,
    branches: tuple[str, ...],
    error_code: str,
    error_message: str,
) -> None:
    try:
        _ = create_backup_refs_for_branches(
            txn_id=txn_id,
            branches=list(branches),
            cwd=repo_root,
        )
    except RuntimeError as error:
        raise AppError(
            code=error_code, message=error_message, details=str(error)
        ) from error


def _remove_backup_refs(
    *,
    repo_root: Path,
    txn_id: str,
    error_code: str,
    error_message: str,
) -> None:
    try:
        remove_backup_refs(txn_id=txn_id, cwd=repo_root)
    except RuntimeError as error:
        raise AppError(
            code=error_code, message=error_message, details=str(error)
        ) from error


def _restore_branch_from_backup_ref(
    *,
    repo_root: Path,
    txn_id: str,
    branch: str,
    backup_oid: str | None,
    error_code: str,
    error_message: str,
) -> None:
    try:
        if backup_oid is None:
            restore_branch_from_backup_ref(txn_id=txn_id, branch=branch, cwd=repo_root)
        else:
            set_branch_head(branch=branch, oid=backup_oid, cwd=repo_root)
    except RuntimeError as error:
        raise AppError(
            code=error_code, message=error_message, details=str(error)
        ) from error


def _restore_backup_command(*, txn_id: str, branch: str) -> str:
    backup_ref = backup_ref_for_branch(txn_id=txn_id, branch=branch)
    return f"git checkout {branch} && git reset --hard {backup_ref}"


def _delete_backup_ref_command(*, txn_id: str, branch: str) -> str:
    return f"git update-ref -d {backup_ref_for_branch(txn_id=txn_id, branch=branch)}"
