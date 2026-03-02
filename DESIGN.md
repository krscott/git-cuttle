# Design Document

This document describes the current, implemented behavior of `git-cuttle`.
It is intentionally scoped to what exists in code today.

## Overview

`git-cuttle` currently ships a small validated CLI surface:

- parsing of shared process flags (`--verbose`, `--destination`)
- repository safety checks (must be in git repo, no in-progress merge/rebase/cherry-pick)
- user-facing structured error formatting
- metadata schema, validation, migration, and atomic persistence helpers
- workspace path derivation helpers
- transactional operation primitive for multi-step branch/worktree mutations
- workspace creation helpers for standard and octopus branches
- non-octopus workspace update helper with upstream rebase behavior
- remote ahead/behind status resolution helpers for tracked workspaces
- list table rendering helpers with unknown-status markers

Higher-level workflow commands (`new`, `list`, `delete`, `prune`, `update`,
`absorb`) are planned but not yet implemented end-to-end in the CLI.

The `new` and non-octopus portions of `update` are partially implemented as
library helpers in `git_cuttle/new.py` and `git_cuttle/update.py`, but are not
yet wired to CLI subcommands.

## Runtime Flow

Entry point: `git_cuttle/__main__.py`

1. Set process title to `gitcuttle`.
2. Load environment variables from `.env` (if present).
3. Parse CLI arguments.
4. Configure logging level (`DEBUG` with `--verbose`, else `INFO`).
5. Run orchestrator.
6. Convert `AppError` to user-facing stderr output and exit with status `2`.

## CLI Contract

Current arguments:

- positional `name` (optional, default `World`)
- `-d, --destination`: print destination path only
- `-v, --verbose`: enable debug logs

Verbose mode can also be enabled via `GITCUTTLE_VERBOSE`.

Argument parsing errors are raised as:

- `error[invalid-arguments]: invalid command arguments`
- with `details:` and actionable `hint:` lines

## Orchestrator Behavior

Current orchestration (`git_cuttle/orchestrator.py`):

1. Verify invocation occurs inside a git repository.
2. Reject execution if any git state marker exists:
   - `MERGE_HEAD`
   - `CHERRY_PICK_HEAD`
   - `REVERT_HEAD`
   - `REBASE_HEAD`
   - `rebase-apply`
   - `rebase-merge`
3. Auto-track repo metadata only for mutating command identifiers:
   - `new`
   - `delete`
   - `prune`
   - `update`
   - `absorb`
4. If `--destination` is set, print resolved current directory and return.
5. Otherwise print greeting `Hello, <name>!`.

All failures above use structured `AppError` with guidance text.

## Error Model

`AppError` fields:

- `code`
- `message`
- optional `details`
- optional `guidance` tuple

Formatting contract (`git_cuttle/errors.py`):

- first line: `error[<code>]: <message>`
- optional details line: `details: ...`
- each guidance entry as: `hint: ...`

## Metadata and Persistence

`git_cuttle/metadata_manager.py` implements a versioned metadata model and
safe file persistence. This module is production-ready as a library but is not
yet wired to workflow commands.

Storage path:

- `$XDG_DATA_HOME/gitcuttle/workspaces.json` when `XDG_DATA_HOME` is set
- otherwise `~/.local/share/gitcuttle/workspaces.json`

Schema:

- current schema version: `1`
- top-level object: `{"version": 1, "repos": {...}}`
- repo and workspace records use typed dataclasses and strict validation

Implemented guarantees:

- schema-version compatibility checks
- v0 -> v1 migration
- pre-migration backup at `workspaces.json.bak.<unix-timestamp>`
- atomic writes via temp file + `fsync` + `os.replace`
- repo key identity must equal canonical git-dir realpath
- workspace key identity must equal branch name
- timestamp and structural invariant validation
- `ensure_repo_tracked(...)` creates/updates repo entries with deterministic
  timestamp behavior while preserving existing `tracked_at`
- auto-tracking chooses `origin` as default remote when available, otherwise
  the first remote name in sorted order

## Workspace Path Helpers

`git_cuttle/workspace_paths.py` provides deterministic path derivation helpers:

- root: `$XDG_DATA_HOME/gitcuttle` or `~/.local/share/gitcuttle`
- repo id: `<repo-slug>-<hash8>` from canonical git-dir path
- branch dir sanitization for filesystem-safe directory names
- deterministic collision suffixing (`-<hash6>`) when sibling branches sanitize
  to the same directory name

These helpers are tested and ready for future command wiring.

## Workspace Creation Helpers

`git_cuttle/new.py` currently provides library-level workspace creation flows:

- `create_standard_workspace(...)`: validates base ref, creates a branch,
  creates a worktree, and persists metadata as `kind="standard"`.
- `create_octopus_workspace(...)`: requires at least two parent refs,
  creates a new branch from the first parent, creates a worktree, performs an
  octopus merge commit with remaining parents in argument order, and persists
  metadata as `kind="octopus"` with ordered `octopus_parents`.

Both flows persist tracked workspace metadata using canonical repo identity and
derived workspace path rules.

## Workspace Update Helper

`git_cuttle/update.py` provides library-level non-octopus update behavior:

- requires `kind="standard"` workspace metadata
- resolves upstream as `<tracked_remote>/<branch>` or `<default_remote>/<branch>`
- emits `error[no-upstream]` when no upstream can be resolved
- fetches upstream remote and verifies the remote-tracking ref exists
- rebases local workspace branch onto upstream using git rebase semantics
- returns before/after branch OIDs to support future dry-run/plan wiring

## Remote Status Helpers

`git_cuttle/remote_status.py` computes ahead/behind status for tracked
workspaces against their configured upstream remote refs and resolves pull
request state metadata for GitHub remotes.

Implemented behavior:

- derive upstream as `<tracked_remote>/<branch>` or `<default_remote>/<branch>`
- return unknown status when local branch or remote-tracking ref is missing
- compute ahead/behind counts using `git rev-list --left-right --count`
- provide per-workspace and per-repo status mapping helpers
- resolve PR state/title/url by branch head via `gh pr list --head <branch>`
- map PR states to prune-compatible values (`open`, `closed`, `merged`,
  `unknown`, `unavailable`)
- mark PR metadata as unavailable when the remote is non-GitHub, `gh` is
  missing, or CLI output cannot be parsed safely
- provide a `RemoteStatusCache` with a default 60-second TTL for list-style
  repeated status lookups
- render list rows into a stable table format with columns:
  - `BRANCH`
  - `KIND`
  - `BASE`
  - `UPSTREAM`
  - `AHEAD`
  - `BEHIND`
  - `PR`
  - `WORKTREE`
- use `?` markers for unknown remote fields (`upstream`, `ahead`, `behind`)

This is currently library-level functionality and is not yet wired to the
`list` command output.

## Transaction Framework

`git_cuttle/transaction.py` now provides a reusable transaction primitive for
future multi-branch/worktree commands.

Implemented behavior:

- explicit ordered transaction steps with `apply` and `rollback` callbacks
- rollback of already-applied steps in reverse order when a later step fails
- `TransactionExecutionError` when execution fails but rollback completes
- `TransactionRollbackError` when rollback is partial, including per-step
  rollback failure details
- explicit partial-state reporting via `TransactionRollbackError.format_partial_state()`
  including deterministic, de-duplicated manual recovery commands
- helper `run_transaction(...)` for one-shot execution with explicit or
  generated transaction ids
- git operation helpers now support transaction rollback primitives for:
  - restoring branch refs from `refs/gitcuttle/txn/<txn-id>/...` backups
  - removing created worktrees during rollback
  - restoring pre-transaction metadata state through step-level rollback

## Testing Scope

Current integration tests cover:

- basic invocation behavior
- destination output contract
- verbose behavior (flag + env)
- outside-repo blocking error guidance
- behavior parity from repo root and worktree
- in-progress git-operation blocking guidance
- invalid-arguments guidance

Unit tests cover metadata schema/migration/validation and workspace path
derivation utilities.

## Planned Work

The multi-branch workflow command set remains planned work and is tracked in
`TODO.md`.
