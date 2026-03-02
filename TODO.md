# Implementation TODO

This file tracks remaining delivery stories. Each story includes both
implementation work and user-visible automated test coverage.

## Stories

- [x] [P0] Story: Make `update` octopus flow fully transactional across all touched refs.
  `DESIGN.md` (Merge strategy) requires multi-branch operations to be atomic,
  with backup refs under `refs/gitcuttle/txn/<txn-id>/...` and full rollback on
  failure. `git_cuttle/update.py::update_octopus_workspace` currently rebases
  parent branches before rebuilding the octopus branch, but only restores the
  octopus branch on failure. Add backup refs and rollback for every touched
  parent branch, and add CLI-level integration coverage for parent-ref rollback
  and backup-ref cleanup.

- [x] [P0] Story: Make `absorb` transactional with deterministic rollback and recovery output.
  `DESIGN.md` requires atomic multi-branch operations and explicit partial-state
  recovery guidance when rollback fails. `git_cuttle/absorb.py::absorb_octopus_workspace`
  mutates parent branches and rebuilds the octopus branch without transaction
  backup refs or coordinated rollback. Wrap absorb in transaction steps that
  snapshot touched refs, restore all refs on failure, and emit deterministic
  recovery commands when rollback is partial; add integration tests for both
  rollback success and rollback-failure reporting.

- [ ] [P1] Story: Transactionalize `new`, `delete`, and `prune` to prevent git/metadata drift.
  `DESIGN.md` requires git ref/worktree changes and metadata writes to be
  rollback-safe as one operation. `git_cuttle/new.py`, `git_cuttle/delete.py`,
  and `git_cuttle/prune.py` currently perform sequential mutations and can leave
  partial state (for example, branch/worktree changed but metadata stale) when
  a later step fails. Introduce shared transaction wiring for these commands and
  add integration tests that inject failures after git mutations and assert full
  recovery of refs, worktrees, metadata, and temporary backup refs.
