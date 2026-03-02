# Implementation TODO

This file tracks required follow-up delivery stories found during PR review.
Each story includes implementation work and user-visible automated coverage.

## Stories

- [ ] [P1] Story: Restore mypy clean run for rollback helper usage.
  `python -m mypy .` currently fails with `attr-defined` errors in
  `tests/test_delete_prune_integration.py` when referencing
  `workspace_transaction.remove_backup_refs`. Update exports or call sites so
  both rollback-failure integration tests type-check cleanly while preserving
  existing behavior.

- [ ] [P2] Story: Ensure workspace-path DESIGN row is backed by CLI integration references.
  `INTEGRATION_TEST_MATRIX.md` marks Workspace path derivation as covered but
  currently references `tests/test_workspace_paths.py` (unit-level). Add/expand
  CLI integration assertions for `<repo-slug>-<hash8>` and deterministic
  collision suffix behavior, then point the matrix row at those integration
  tests.
