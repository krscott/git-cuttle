# Implementation TODO

This file tracks remaining delivery stories. Each story includes both
implementation work and user-visible automated test coverage.

## Stories

- [ ] [P0] Story: Ship CLI subcommand architecture for `new`, `list`, `delete`, `prune`,
  `update`, and `absorb`.
  Include argparse subparser wiring, shared flag conventions, command dispatch
  through orchestrator, and black-box CLI tests for help text, argument
  validation, and per-command invocation paths. This must replace the current
  template greeting CLI behavior.

- [ ] [P0] Story: Deliver `gitcuttle new` end-to-end for standard and octopus workspace
  creation.
  Include base resolution rules, branch existence checks (local and upstream),
  deterministic destination path behavior, metadata persistence, and integration
  tests that execute the CLI from both repo root and worktree contexts.
  Explicitly align base default behavior with `DESIGN.md` (default to current
  commit) and enforce remote branch-existence checks when upstream context
  exists.

- [ ] [P1] Story: Deliver `gitcuttle list` end-to-end with stable table rendering and
  graceful unknown markers.
  Include metadata loading, remote ahead/behind + PR status resolution,
  short-TTL caching behavior, and integration tests for online, offline,
  unauthenticated, and non-GitHub remote scenarios. Ensure output columns and
  PR state presentation match `DESIGN.md` (including repo, dirty, and
  description fields).

- [ ] [P0] Story: Deliver `gitcuttle delete` end-to-end with safety gates and plan
  output contracts.
  Include tracked-workspace validation, dirty/ahead/no-upstream blocking,
  current-workspace deletion protection, `--force`, `--dry-run`, and `--json`
  behavior, with integration tests that assert both blocked and allowed flows.
  Explicitly resolve current implementation drift where `--force` currently
  bypasses current-workspace protection.

- [ ] [P0] Story: Deliver `gitcuttle prune` end-to-end for merged-PR and missing-branch
  cleanup.
  Include prune candidate selection, unknown PR status handling as not merged,
  safety gates with force overrides, and integration tests for dry-run/json and
  mutating prune outcomes. Explicitly add ahead-of-remote and no-upstream
  safety gates required by `DESIGN.md`.

- [ ] [P1] Story: Deliver `gitcuttle update` end-to-end for standard and octopus
  workspaces.
  Include non-octopus upstream rebasing, octopus parent update/rebuild/replay
  behavior, no-upstream error paths, and integration tests validating branch
  history transformations and conflict/error guidance.

- [ ] [P1] Story: Deliver `gitcuttle absorb` end-to-end for octopus workspaces.
  Include explicit target mode, interactive target selection mode, heuristic
  mapping with ambiguity failures, and integration tests that verify commit
  movement semantics and user-facing failure messaging. Validate implementation
  semantics against `DESIGN.md` absorb wording and update behavior/tests if
  needed for strict contract alignment.

- [ ] [P0] Story: Enforce transactional safety guarantees for all mutating commands.
  Include backup ref lifecycle, rollback of refs/worktrees/metadata, and
  deterministic partial-state recovery output, with integration tests that
  inject failures mid-transaction and during rollback.

- [ ] [P0] Story: Finalize metadata lifecycle behavior through CLI flows.
  Include auto-tracking for mutating commands only, no-tracking side effects for
  read-only commands, migration + backup behavior in real command execution, and
  integration tests that verify persistence invariants over repeated runs.
  Also validate metadata path/fallback behavior used in implementation and keep
  docs/spec wording consistent.

- [x] [P2] Story: Align user documentation with shipped CLI behavior.
  Include README command examples, troubleshooting guidance for blocked states,
  and test-backed validation of documented command output snippets where
  practical.
