# Implementation TODO

This file tracks remaining delivery stories. Each story includes both
implementation work and user-visible automated test coverage.

## Stories

- [x] [P1] Story: Ensure metadata write is truly last in delete/prune success paths.
  `DESIGN.md` minimum rollback contract says metadata writes MUST be last after
  git ref/worktree mutations. `git_cuttle/delete.py` and `git_cuttle/prune.py`
  still call `cleanup_backup_refs_post_commit` after `write-metadata`, which
  performs `git update-ref -d` mutations after metadata persistence. Rework
  backup-ref lifecycle so successful delete/prune runs do not mutate refs after
  metadata is committed, while preserving deterministic rollback/recovery.

- [x] [P1] Story: Add deterministic recovery commands for branch-restore rollback failures.
  `DESIGN.md` requires deterministic recovery commands whenever rollback is
  partial. In `delete`/`prune`, rollback of branch deletion uses
  `rollback_restore_branch(...)` but those `TransactionStep`s do not publish
  `recovery_commands`, so a failed restore can emit `transaction-rollback-failed`
  without actionable branch repair commands. Add explicit branch-restore
  recovery commands (and CLI integration tests) for these rollback-failure paths.
