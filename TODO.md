# Implementation TODO

This file tracks remaining delivery stories. Each story includes both
implementation work and user-visible automated test coverage.

## Stories

- [x] [P1] Story: Enforce `DESIGN.md` metadata-last ordering in transactional delete/prune flows.
  `DESIGN.md` minimum rollback contract states metadata writes MUST be last after
  git ref/worktree mutations. `git_cuttle/delete.py` and `git_cuttle/prune.py`
  currently run backup-ref cleanup after `write-metadata`, which is another ref
  mutation after metadata. Reorder transaction sequencing (or split post-commit
  cleanup semantics) so metadata is truly the final state mutation while still
  preserving deterministic rollback and recovery behavior.

- [ ] [P1] Story: Guarantee deterministic manual recovery commands for worktree-rollback failures.
  `DESIGN.md` requires deterministic recovery commands whenever rollback is
  partial. In `new`/`delete`/`prune`, rollback failures in worktree restoration
  steps can currently surface without step-specific recovery commands. Add
  explicit `TransactionStep.recovery_commands` for worktree rollback paths and
  cover these failure modes with CLI integration tests that assert actionable
  recovery output.

- [ ] [P2] Story: Add CLI integration coverage for octopus `update` partial-rollback reporting.
  `DESIGN.md` user-visible failure contracts require exact partial-state output
  and deterministic recovery commands when rollback fails. `absorb` has CLI
  coverage for this path, but `update` currently only covers rollback-success
  scenarios. Add a rollback-failure integration test (for example via hooks that
  invalidate backup refs mid-transaction) and assert `transaction-rollback-failed`
  output includes partial state plus recovery commands.
