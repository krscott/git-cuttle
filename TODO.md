# Implementation TODO

This file tracks remaining delivery stories. Each story includes both
implementation work and user-visible automated test coverage.

## Stories

- [x] [P0] Story: Fix delete dry-run JSON integration contract to match DESIGN safety gates.
  `tests/test_delete_prune_integration.py::test_delete_dry_run_json_outputs_plan_without_changes`
  currently expects success without an upstream and fails against current behavior.
  `DESIGN.md` requires delete dry-run to enforce the same no-upstream safety
  block as mutating delete unless `--force` is used. Update the integration
  scenario and assertions so dry-run JSON still has no side effects while
  honoring the required upstream gate.

- [ ] [P1] Story: Add integration coverage proving `list` status cache TTL behavior.
  `DESIGN.md` requires `list` to use a short status cache TTL (default 60s),
  but current matrix marks this as planned and coverage is unit-level only.
  Add black-box CLI integration tests that demonstrate cache reuse within TTL
  and refresh after TTL expiry, and update `INTEGRATION_TEST_MATRIX.md` once
  this requirement is covered.
