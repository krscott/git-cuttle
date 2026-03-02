# Backlog

Nice-to-have improvements discovered during PR review.

- [ ] Add a small PR template for DESIGN-alignment checks (requirements touched,
  integration coverage updated, matrix rows referenced) to reduce review churn.

- [ ] Add a fast pre-commit hook or CI preflight target that runs `./format.sh`
  locally before push to catch formatting drift earlier.

- [ ] Add a focused `make review` (or script) target that runs matrix lint,
  key integration subsets, and DESIGN contract sanity checks in one command.
