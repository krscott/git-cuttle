# Implementation TODO

## Foundation

- [x] Finalize module boundaries (`CLI`, `Orchestrator`, `Git ops`, `Metadata manager`) and wire entry points.
- [x] Define shared error model and user-facing error formatting for all commands.
- [x] Standardize command/flag conventions (short + long flags, shared `--destination` behavior for navigation-style commands).

## Metadata and Persistence

- [x] Implement `workspaces.json` schema v1 read/write models with validation and invariants.
- [x] Use git dir realpath as canonical repo identity and enforce repo/workspace key consistency.
- [x] Implement atomic metadata writes (temp file + fsync + rename).
- [x] Implement schema migration framework with pre-migration backup creation.
- [x] Implement workspace path derivation (`<repo-id>/<branch-dir>`) including deterministic collision handling.

## Core Safety and Transactions

- [x] Implement transactional operation framework for multi-branch/worktree changes.
- [x] Implement git backup refs under `refs/gitcuttle/txn/<txn-id>/...` for touched branches.
- [x] Implement full rollback for refs, worktrees, and metadata on failure.
- [x] Implement rollback-failure reporting with explicit partial-state output and deterministic recovery commands.
- [x] Enforce clean-operation policy (no merge/rebase/cherry-pick conflicts accepted).

## Repository Context and Tracking

- [x] Implement repo context detection and hard error outside git repos.
- [x] Implement auto-tracking for mutating commands only (`new`, `delete`, `prune`, `update`, `absorb`).
- [x] Ensure commands behave consistently from repo root and worktree directories.

## Command Implementation

- [ ] Implement `gitcuttle new` for standard workspace creation (base resolution, branch creation, destination output).
- [ ] Implement octopus `gitcuttle new` (n-way merge creation, ordered parent tracking).
- [ ] Implement `gitcuttle list` table output with required columns and graceful unknown markers.
- [ ] Implement `gitcuttle delete` with tracked-workspace checks, safety gates, `--force`, `--dry-run`, and `--json` plan output.
- [ ] Implement `gitcuttle prune` with merged-PR or missing-local-branch criteria, safety gates, `--force`, `--dry-run`, and `--json` plan output.
- [ ] Implement `gitcuttle update` for non-octopus branches (upstream rebase rules + no-upstream error path).
- [ ] Implement octopus `gitcuttle update` rebuild flow (parent updates, new n-way merge, replay post-merge commits, no direct octopus upstream rebase).
- [ ] Implement `gitcuttle absorb` (explicit target branch mode, interactive `-i`, heuristic mode with confidence failure behavior).

## Remote/PR Integration and Caching

- [ ] Implement remote ahead/behind status integration per tracked workspace.
- [ ] Implement PR status/title integration against each workspace's tracked remote.
- [ ] Implement short-TTL status cache (default 60s) used by `list`.
- [ ] Ensure cache refresh never creates tracking entries.
- [x] Ensure prune treats unknown/unavailable PR status as not merged.

## Output and UX Contracts

- [x] Implement actionable guidance messages for all blocked/error states.
- [x] Implement `--destination` output contract (path-only stdout mode).
- [x] Implement human-readable dry-run plans and machine-readable `--json` plans.

## Testing

- [x] Build integration test matrix covering user-visible behavior and command contracts in `DESIGN.md`.
- [ ] Add integration tests for safety-critical flows (transaction rollback, rollback failure path, no-upstream blocking, force overrides).
- [ ] Add integration tests for octopus workflows (`new`, `update`, `absorb`) including ambiguity handling.
- [ ] Add integration tests for delete/prune edge cases (current workspace deletion block, missing local branch prune, unknown PR state behavior).
- [x] Add integration tests for metadata/migration behavior (schema validation, backup creation, migration correctness).

## Documentation and Release Readiness

- [x] Keep `DESIGN.md` and implementation behavior synchronized as features land.
- [x] Add/update user-facing command docs and examples for all major flows.
- [x] Add operational troubleshooting docs for rollback recovery and common git-state errors.
