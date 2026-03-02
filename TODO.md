# Implementation TODO

This file tracks required follow-up delivery stories found during PR review.
Each story includes implementation work and user-visible automated coverage.

## Stories

- [ ] [P1] Story: Add CLI integration coverage for workspace path collision handling.
  `DESIGN.md` requires deterministic suffixes when two branch names sanitize to
  the same workspace directory. Add an end-to-end `gitcuttle new` integration
  test that creates colliding branch names, asserts unique deterministic
  `--destination` paths, and validates persisted metadata remains keyed by the
  original unsanitized branch names.

- [ ] [P1] Story: Add integration-first coverage for metadata schema invariants.
  The integration matrix still points key persistent-data requirements to unit
  tests (`tests/test_metadata_manager.py`). Add black-box CLI integration cases
  that exercise canonical repo identity and schema invariant failures through
  command flows, then update `INTEGRATION_TEST_MATRIX.md` references so these
  DESIGN requirements are backed by integration tests.
