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
