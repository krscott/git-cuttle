from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import cast
from uuid import uuid4


@dataclass(kw_only=True, frozen=True)
class TransactionStep:
    name: str
    apply: "StepFn"
    rollback: "StepFn"
    recovery_commands: tuple[str, ...] = ()


StepFn = Callable[[], None]


@dataclass(kw_only=True, frozen=True)
class RollbackFailure:
    step_name: str
    error: Exception
    recovery_commands: tuple[str, ...] = ()


@dataclass(kw_only=True, frozen=True)
class TransactionExecutionError(RuntimeError):
    txn_id: str
    failed_step_name: str
    cause: Exception
    rolled_back_steps: tuple[str, ...]

    def __str__(self) -> str:
        return (
            f"transaction {self.txn_id} failed during step '{self.failed_step_name}': "
            f"{self.cause}"
        )


@dataclass(kw_only=True, frozen=True)
class TransactionRollbackError(RuntimeError):
    txn_id: str
    failed_step_name: str
    cause: Exception
    rollback_failures: tuple[RollbackFailure, ...]
    rolled_back_steps: tuple[str, ...]

    def recovery_commands(self) -> tuple[str, ...]:
        commands: list[str] = []
        seen: set[str] = set()
        for failure in self.rollback_failures:
            for command in failure.recovery_commands:
                if command in seen:
                    continue
                commands.append(command)
                seen.add(command)
        return tuple(commands)

    def format_partial_state(self) -> str:
        rolled_back = ", ".join(self.rolled_back_steps) if self.rolled_back_steps else "(none)"
        lines = [
            f"transaction id: {self.txn_id}",
            f"failed step: {self.failed_step_name}",
            f"operation error: {self.cause}",
            f"rolled back steps: {rolled_back}",
            "rollback failures:",
        ]
        for failure in self.rollback_failures:
            lines.append(f"- {failure.step_name}: {failure.error}")

        recovery_commands = self.recovery_commands()
        if recovery_commands:
            lines.append("deterministic recovery commands:")
            lines.extend(f"- {command}" for command in recovery_commands)
        else:
            lines.append("deterministic recovery commands: (none provided)")
        return "\n".join(lines)

    def __str__(self) -> str:
        failed_rollbacks = ", ".join(
            f"{failure.step_name}: {failure.error}" for failure in self.rollback_failures
        )
        return (
            f"transaction {self.txn_id} failed during step '{self.failed_step_name}' and "
            f"rollback was partial ({failed_rollbacks})"
        )


@dataclass(kw_only=True)
class Transaction:
    txn_id: str = field(default_factory=lambda: uuid4().hex)
    _steps: list[TransactionStep] = field(
        default_factory=lambda: cast(list[TransactionStep], [])
    )

    def add_step(self, step: TransactionStep) -> None:
        self._steps.append(step)

    def add_steps(self, steps: Iterable[TransactionStep]) -> None:
        for step in steps:
            self._steps.append(step)

    def run(self) -> None:
        completed_steps: list[TransactionStep] = []

        for step in self._steps:
            try:
                step.apply()
                completed_steps.append(step)
            except Exception as operation_error:
                rollback_failures: list[RollbackFailure] = []
                rolled_back_step_names: list[str] = []

                for completed_step in reversed(completed_steps):
                    try:
                        completed_step.rollback()
                        rolled_back_step_names.append(completed_step.name)
                    except Exception as rollback_error:
                        rollback_failures.append(
                            RollbackFailure(
                                step_name=completed_step.name,
                                error=rollback_error,
                                recovery_commands=completed_step.recovery_commands,
                            )
                        )

                rolled_back_steps = tuple(rolled_back_step_names)
                if rollback_failures:
                    raise TransactionRollbackError(
                        txn_id=self.txn_id,
                        failed_step_name=step.name,
                        cause=operation_error,
                        rollback_failures=tuple(rollback_failures),
                        rolled_back_steps=rolled_back_steps,
                    ) from operation_error

                raise TransactionExecutionError(
                    txn_id=self.txn_id,
                    failed_step_name=step.name,
                    cause=operation_error,
                    rolled_back_steps=rolled_back_steps,
                ) from operation_error


def run_transaction(
    *,
    steps: Iterable[TransactionStep],
    txn_id: str | None = None,
) -> str:
    transaction = Transaction(txn_id=txn_id or uuid4().hex)
    transaction.add_steps(steps)
    transaction.run()
    return transaction.txn_id
