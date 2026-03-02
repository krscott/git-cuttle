# Implementation TODO

This file tracks required follow-up delivery stories found during PR review.
Each story includes implementation work and user-visible automated coverage.

## Stories

- [ ] [P1] Story: Add black-box CLI coverage for `delete` tracked-state
  guidance paths.
  `DESIGN.md` requires `gitcuttle delete` to fail with actionable guidance when
  (a) deleting the currently checked-out workspace and (b) the target branch is
  not tracked. Current tests mostly exercise internal helpers. Add subprocess
  CLI integration tests that assert user-facing stderr guidance and exit codes,
  then update `INTEGRATION_TEST_MATRIX.md` references to point to those CLI
  tests.

- [ ] [P1] Story: Restore green PR checks by resolving formatting drift.
  PR #2 currently shows a failing `format` check. Apply `./format.sh`, commit
  the resulting formatting-only changes, and verify CI reports both `build` and
  `format` checks as passing.
