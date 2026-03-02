# Implementation TODO

This file tracks required follow-up delivery stories found during PR review.
Each story includes implementation work and user-visible automated coverage.

## Stories

- [x] [P0] Story: Restore formatting compliance so CI passes.
  PR #2 currently fails the `format` check. Run `./format.sh`, commit the
  formatter changes, and ensure CI no longer reports formatting drift.

- [ ] [P1] Story: Add integration coverage for atomic metadata write guarantees.
  `DESIGN.md` requires user-visible requirements to be backed by integration
  tests. The atomic metadata write contract is currently documented as covered
  by unit tests in `INTEGRATION_TEST_MATRIX.md`; add an integration scenario
  that exercises crash-safe/atomic persistence behavior through CLI flows and
  update matrix references accordingly.
