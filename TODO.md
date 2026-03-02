# Implementation TODO

This file tracks required follow-up delivery stories found during PR review.
Each story includes implementation work and user-visible automated coverage.

## Stories

- [ ] [P1] Story: Add missing `new` branch-conflict integration coverage.
  `DESIGN.md` requires `gitcuttle new` to reject target branches that already
  exist locally or on tracked remotes, and to use local-only checks when no
  remote context exists. Add CLI integration tests for these branches and update
  `INTEGRATION_TEST_MATRIX.md` references so the `new standard` row points to
  concrete conflict-coverage test IDs.

- [ ] [P1] Story: Prove repo-root/worktree parity for mutating commands.
  `DESIGN.md` states command behavior MUST be the same whether invoked from repo
  root or a worktree directory. Add/expand CLI integration tests for
  `delete`, `prune`, `update`, and `absorb` parity (not just `new`/default
  invocation), then update matrix references to those parity assertions.
