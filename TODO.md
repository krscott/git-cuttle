# Implementation TODO

This file tracks remaining delivery stories. Each story includes both
implementation work and user-visible automated test coverage.

## Stories

- [x] [P0] Story: Ship CLI subcommand architecture for `new`, `list`, `delete`, `prune`,
  `update`, and `absorb`.
  Include argparse subparser wiring, shared flag conventions, command dispatch
  through orchestrator, and black-box CLI tests for help text, argument
  validation, and per-command invocation paths. This must replace the current
  template greeting CLI behavior.

- [x] [P0] Story: Deliver `gitcuttle new` end-to-end for standard and octopus workspace
  creation.
  Include base resolution rules, branch existence checks (local and upstream),
  deterministic destination path behavior, metadata persistence, and integration
  tests that execute the CLI from both repo root and worktree contexts.
  Explicitly align base default behavior with `DESIGN.md` (default to current
  commit) and enforce remote branch-existence checks when upstream context
  exists.

- [x] [P1] Story: Deliver `gitcuttle list` end-to-end with stable table rendering and
  graceful unknown markers.
  Include metadata loading, remote ahead/behind + PR status resolution,
  short-TTL caching behavior, and integration tests for online, offline,
  unauthenticated, and non-GitHub remote scenarios. Ensure output columns and
  PR state presentation match `DESIGN.md` (including repo, dirty, and
  description fields).

- [x] [P0] Story: Deliver `gitcuttle delete` end-to-end with safety gates and plan
  output contracts.
  Include tracked-workspace validation, dirty/ahead/no-upstream blocking,
  current-workspace deletion protection, `--force`, `--dry-run`, and `--json`
  behavior, with integration tests that assert both blocked and allowed flows.
  Explicitly resolve current implementation drift where `--force` currently
  bypasses current-workspace protection.

- [x] [P0] Story: Deliver `gitcuttle prune` end-to-end for merged-PR and missing-branch
  cleanup.
  Include prune candidate selection, unknown PR status handling as not merged,
  safety gates with force overrides, and integration tests for dry-run/json and
  mutating prune outcomes. Explicitly add ahead-of-remote and no-upstream
  safety gates required by `DESIGN.md`.

- [x] [P1] Story: Deliver `gitcuttle update` end-to-end for standard and octopus
  workspaces.
  Include non-octopus upstream rebasing, octopus parent update/rebuild/replay
  behavior, no-upstream error paths, and integration tests validating branch
  history transformations and conflict/error guidance.

- [x] [P1] Story: Deliver `gitcuttle absorb` end-to-end for octopus workspaces.
  Include explicit target mode, interactive target selection mode, heuristic
  mapping with ambiguity failures, and integration tests that verify commit
  movement semantics and user-facing failure messaging. Validate implementation
  semantics against `DESIGN.md` absorb wording and update behavior/tests if
  needed for strict contract alignment.

- [x] [P0] Story: Enforce transactional safety guarantees for all mutating commands.
  Include backup ref lifecycle, rollback of refs/worktrees/metadata, and
  deterministic partial-state recovery output, with integration tests that
  inject failures mid-transaction and during rollback.

- [x] [P0] Story: Finalize metadata lifecycle behavior through CLI flows.
  Include auto-tracking for mutating commands only, no-tracking side effects for
  read-only commands, migration + backup behavior in real command execution, and
  integration tests that verify persistence invariants over repeated runs.
  Also validate metadata path/fallback behavior used in implementation and keep
  docs/spec wording consistent.

- [x] [P2] Story: Align user documentation with shipped CLI behavior.
  Include README command examples, troubleshooting guidance for blocked states,
  and test-backed validation of documented command output snippets where
  practical.

## PR Review Follow-ups

- [x] [P0] Story: Support branch-name omission in `gitcuttle new` per DESIGN.
  Allow `gitcuttle new` without `-b/--branch`, generate a random inverse-hex
  workspace branch name, and ensure destination/output + metadata behavior stay
  consistent with explicit branch mode. Add CLI integration tests for omitted
  branch generation and uniqueness.

- [x] [P0] Story: Align octopus `update` with parent-update contract.
  Update each tracked parent individually before octopus rebuild (rebase parent
  onto upstream when upstream exists; otherwise use local parent tip), then
  rebuild and replay post-merge commits. Add integration tests asserting parent
  update semantics and resulting commit graph.

- [x] [P0] Story: Enforce atomic rollback contracts in mutating multi-step flows.
  Wire transaction/backup-ref primitives into command paths that mutate multiple
  refs/worktrees (`new`, `delete`, `prune`, `update`, `absorb`) so failures
  restore refs, worktrees, and metadata deterministically, including rollback
  failure reporting with exact partial state and recovery commands.

- [x] [P1] Story: Strengthen conflict guidance on merge/rebase/cherry-pick errors.
  Ensure conflict-prone git operation failures surface actionable guidance
  matching DESIGN requirements (how to restore git to an operable state), and
  add integration assertions for guidance text on blocked/conflict flows.

- [x] [P1] Story: Fix delete guidance and close MUST-level integration gaps.
  For untracked workspace deletion, include guidance to delete via git CLI as
  required by DESIGN. Add integration tests for: invalid base-ref hinting,
  absorb failure when current workspace is non-octopus, prune missing-local-
  branch cleanup (metadata + directory), and list cache-refresh behavior that
  never creates tracking entries.

- [ ] [P0] Story: Enforce transaction + backup-ref atomicity for all mutating
  command paths.
  Wire `new`, `delete`, `prune`, `update`, and `absorb` through a shared
  transaction runner that creates `refs/gitcuttle/txn/<txn-id>/...` backups
  before ref mutations, applies git/worktree changes before metadata writes,
  and restores refs/worktrees/metadata on failure. Add integration coverage for
  mid-flight failures and backup-ref cleanup.

- [x] [P0] Story: Surface rollback partial-state recovery contract in CLI error
  handling.
  Catch transaction rollback failures at the CLI boundary and print exact
  partial-state details plus deterministic recovery commands per DESIGN. Add
  integration tests that assert user-visible stderr content for rollback-failed
  scenarios.

- [ ] [P1] Story: Align `gitcuttle absorb <parent>` explicit-target semantics
  with DESIGN.
  Replace direct cherry-pick/reset behavior with the required rebase of
  post-merge commits onto the selected parent and octopus merge
  rebase/reconstruction flow. Add commit-graph integration assertions for
  explicit-target absorb behavior.

- [x] [P1] Story: Use actual git upstream configuration for `update` decisions.
  For non-octopus updates, require and use the branch's configured upstream
  (error when absent). For octopus parent updates, rebase each parent only when
  that parent has an upstream configured; otherwise use local tip. Add
  integration tests for upstream-present and upstream-absent cases.
