# Implementation TODO

This file tracks remaining delivery stories. Each story includes both
implementation work and user-visible automated test coverage.

## Stories

- [x] [P0] Story: Make `AppError` compatible with Python exception traceback handling.
  Current `@dataclass(frozen=True)` behavior can raise `FrozenInstanceError`
  while propagating exceptions through context managers (observed under pytest),
  masking the real command failure. Preserve stable error formatting while
  allowing normal exception traceback assignment and add regression coverage.

- [ ] [P0] Story: Align delete dry-run integration expectations with DESIGN safety gates.
  `DESIGN.md` requires delete to block when no upstream is configured unless
  `--force` is provided; current integration tests still expect successful
  dry-run output in no-upstream repos. Update integration fixtures/expectations
  so `delete --dry-run` and `delete --dry-run --json` reflect the same upstream
  safety contract as mutating delete.

- [ ] [P1] Story: Refresh integration contract documentation to match shipped coverage.
  `INTEGRATION_TEST_MATRIX.md` still marks major command and safety requirements
  as `planned` despite implemented tests. Reconcile matrix status entries with
  current test suite and add a lightweight check that prevents future drift.
