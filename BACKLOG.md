# Backlog

Nice-to-have improvements discovered during PR review.

- [ ] Add a small PR template for DESIGN-alignment checks (requirements touched,
  integration coverage updated, matrix rows referenced) to reduce review churn.

- [ ] Add a fast pre-commit hook or CI preflight target that runs `./format.sh`
  locally before push to catch formatting drift earlier.

- [ ] Add a focused `make review` (or script) target that runs matrix lint,
  key integration subsets, and DESIGN contract sanity checks in one command.

- [ ] Add a matrix lint rule that flags references to non-integration tests in
  `INTEGRATION_TEST_MATRIX.md` (for example rows that point at unit-only files).

- [ ] Add a CI job that regenerates and uploads a DESIGN compliance report
  artifact (covered/planned counts by section) to make review regressions
  easier to spot.

- [ ] Add a required CI type-check gate that runs both `python -m mypy .` and
  `python -m pyright` on pull requests, so typed-test regressions are caught
  before review handoff.

- [ ] Add a tiny automation script that verifies every `covered` matrix row in
  `INTEGRATION_TEST_MATRIX.md` references at least one `@pytest.mark.integration`
  test ID.

- [ ] Add a `design-contract-audit` helper that compares `DESIGN.md` MUST
  statements against matrix rows and reports missing/weakly-referenced
  requirements before review.

- [ ] Add reusable integration fixtures for repo/worktree parity scenarios to
  reduce duplication across command parity tests and make contract gaps cheaper
  to cover.

- [ ] Add a matrix lint rule that flags user-visible command rows pointing only
  at helper-level tests (no subprocess `gitcuttle` invocation), so compliance
  claims stay tied to black-box behavior.

- [ ] Add a lightweight CI guard that fails when PR checks are red but
  `TODO.md` has no open P1 remediation story, to keep review follow-up tracking
  aligned with merge blockers.

- [ ] Add a DESIGN contract snapshot test that fails when new/edited `MUST`
  requirements are introduced without corresponding `INTEGRATION_TEST_MATRIX.md`
  rows, so review drift is caught at commit time.

- [ ] Add an end-to-end smoke command (`python -m pytest -m integration -k
  "destination or parity or rollback"`) to speed up local validation of the
  highest-risk DESIGN contracts before pushing.
