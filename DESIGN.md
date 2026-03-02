# Design Document

This document outlines the design, architecture, and components of the
`git-cuttle` application. It serves as a comprehensive guide for understanding
and reproducing the system's functionality.

## Overview

`git-cuttle` is a Command Line Interface (CLI) application for managing git
multi-branch workflows.

## Normative Language

The key words `MUST`, `MUST NOT`, `SHOULD`, `SHOULD NOT`, and `MAY` in this
document are to be interpreted as described in RFC 2119.

## Design Methodology

In descending order, this project optimizes for:

1. Correctness - ops MUST result in a good state
2. Reliability - ops SHOULD be reproducible
3. User-friendly - ops SHOULD have a minimal interface and useful error messages
4. Speed - ops SHOULD be efficient

User-visible requirements listed in this document MUST have corresponding
integration tests. Wherever possible, tests SHOULD be implemented first
(Red-Green-Refactor).

## Architecture

The application is divided into distinct modules

- CLI (`cli.py` + `__main__.py`): Parses argv/env, configures process state/logging,
  and maps failures to user-facing errors.
- Orchestrator (`orchestrator.py`): Coordinates command flow and enforces
  high-level policy checks before invoking lower-level modules.
- Git ops (`git_ops.py`): Wraps git/gh CLI interaction in testable Python
  functions.
- Metadata manager (`metadata_manager.py`): Owns metadata storage locations and
  persistence helpers for `workspaces.json`.

## Persistent Data

All user data MUST be stored in `$XDG_DATA_HOME/gitcuttle/workspaces.json`.

The schema MUST be versioned with a `"version": int` key.

When the schema version changes, the app MUST auto-migrate data to the latest
version and create a timestamped backup before writing.

Backups MUST be written before migration as:
`$XDG_DATA_HOME/gitcuttle/workspaces.json.bak.<unix-timestamp>`.

This data MAY become outdated between invocations, so it MUST be updated before
making filesystem changes.

### `workspaces.json` schema

`workspaces.json` MUST have this structure:

```json
{
  "version": 1,
  "repos": {
    "<git_dir_realpath>": {
      "git_dir": "<absolute realpath to .git dir>",
      "repo_root": "<absolute repo root path>",
      "default_remote": null,
      "tracked_at": "<ISO-8601 timestamp>",
      "updated_at": "<ISO-8601 timestamp>",
      "workspaces": {
        "<branch_name>": {
          "branch": "<git branch name>",
          "worktree_path": "<absolute path>",
          "tracked_remote": null,
          "kind": "standard | octopus",
          "base_ref": "<branch or commit used as base>",
          "octopus_parents": ["<branch>", "<branch>"],
          "created_at": "<ISO-8601 timestamp>",
          "updated_at": "<ISO-8601 timestamp>"
        }
      }
    }
  }
}
```

Field types:

- `default_remote`: `string | null`
- `tracked_remote`: `string | null`

Schema invariants:

- The canonical repo identity key MUST be the realpath of the git directory
  (`<git_dir_realpath>`).
- `repos[<git_dir_realpath>].git_dir` MUST match the map key exactly.
- `default_remote` and `tracked_remote` MAY be `null` when no remote context is
  configured.
- Workspace map keys are branch names and MUST match
  `workspaces[...].branch` exactly.
- `worktree_path` MUST be unique within a repo.
- `kind=standard` MUST have `octopus_parents=[]`.
- `kind=octopus` MUST have `octopus_parents` with at least two branches.
- Octopus parent order is significant and MUST be preserved exactly as entered.
- Branch names are stored unsanitized in metadata. Any sanitized filesystem
  directory naming is derived and not used as identity.

### Status cache

`list` MUST use a short TTL cache (default: 60 seconds) for remote/PR status.
Cache refresh MUST NOT create new repo tracking entries.

### Workspace path derivation

Workspace paths MUST use:

`$XDG_DATA_HOME/gitcuttle/<repo-id>/<branch-dir>`

- `<repo-id>` MUST be `<repo-slug>-<repo-hash8>`, where:
  - `<repo-slug>` is a filesystem-safe slug of the repo name
  - `<repo-hash8>` is the first 8 hex chars of `sha256(<git_dir_realpath>)`
- `<branch-dir>` MUST be derived from a stable sanitized branch name.
- If two branch names sanitize to the same `<branch-dir>`, the command MUST
  append a deterministic short suffix derived from the original branch name
  (for example `-<hash6>`) to avoid collisions.

## Command Scope and Tracking

- Mutating commands (`new`, `delete`, `prune`, `update`, `absorb`) MUST ensure
  the current repo is tracked in `workspaces.json`.
- Read-only commands (for example, `list`) MUST NOT create tracking entries.
- If `gitcuttle` is run outside a git repo, it MUST exit with a clear error and
  guidance to run from within a git repository.

## Definitions

- workspace: A git workspace, either the original repo or a worktree dir
- octopus: A branch that is on top of an n-way merge

## Changing Directory

It is not possible to `cd` from python. For commands that "change directory":
- Commands MUST NOT change the user's shell directory from within `gitcuttle`.
- By default, commands MUST output instructions for changing directory or
  setting up an alias
- Commands MUST accept a `--destination` flag and output only the directory to
  stdout for use by user aliases or shell functions

`--destination` MUST be a shared convention for any current or future command
that conceptually navigates the user to a workspace path.

## Merge strategy

Commands MUST only perform clean merge/rebase/cherry-pick operations. If an
operation results in a git conflict, the command MUST show an error message
with a suggestion on how to get git into a state that would allow the
operation.

Operations that touch multiple branches/worktrees MUST be atomic. If a failure
occurs, roll back all touched branches, worktrees, and metadata to their
pre-command state.

If rollback itself fails, commands MUST exit non-zero and MUST print:

- The exact partial state that remains
- Deterministic recovery commands the user can run to restore consistency

Minimum rollback mechanism contract:

- Before mutating refs, commands MUST create temporary backup refs under
  `refs/gitcuttle/txn/<txn-id>/...` for each touched branch.
- Commands MUST apply git ref/worktree changes before writing metadata.
- Metadata write MUST be last and MUST be atomic (write temp file, fsync,
  rename).
- On failure, commands MUST restore refs from backup refs, restore metadata from
  pre-command snapshot, and clean up temporary refs.

## Use Cases

In all cases, when a command is executed:

- Commands MUST work the same regardless if run from original repo dir
  or from worktree dir
- All short flags SHOULD also have long flags (e.g. `-b,--branch`)

### Creating a new branch and worktree

```
$ gitcuttle new [BRANCH] [-b NAME]
```

- The command MUST create a new branch and worktree in
  `$XDG_DATA_HOME/gitcuttle/<repo-id>/<branch-dir>`
- `BRANCH` is the base branch/commit. If not provided, the command MUST use the
  current commit as the base
- `-b, --branch NAME` is the new branch name to create
- If BRANCH is given but does not exist, commands MUST show an error and
  suggest `new -b NAME` (no BRANCH)
- Branch name MUST be provided with `-b NAME` or generated using a random
  inverse hex (e.g. `workspace-zyxwvut`)
- If given branch name contains `/`, it MUST be sanitized in the dir name,
  but kept in the git branch name. The sanitization mapping MUST be stable.
- If sanitization causes a directory-name collision, commands MUST append a
  deterministic short suffix derived from the original branch name.
- If branch already exists locally or on its tracked remote, commands MUST show
  an error message
- If no tracked remote/upstream context exists, branch-exists checks MUST be
  local-only
- Commands MUST print destination path/instructions and MUST NOT attempt to
  change the caller's cwd

#### Creating an octopus branch

```
$ gitcuttle new BRANCH [BRANCH...] [-b NAME]
```

- The command MUST create a new workspace and branch that is an n-way (octopus)
  merge with the given branches
- The command MUST track all bases in `workspaces.json`
- The command MUST preserve and persist parent branch order exactly as provided

### List workspaces

```
$ gitcuttle list
```

Table of tracked workspaces (leave blank if n/a)
- repo name
- branch name
- dirty status
- remote status: ahead/behind
- PR status: draft/open/merged
- description (PR title or last commit)

If remote/PR status cannot be fetched (offline, auth, unsupported remote),
commands MUST show unknown/blank markers and continue.

### Delete workspace

```
$ gitcuttle delete BRANCH [--dry-run] [--json] [--force]
```

- The command MUST delete the tracked BRANCH workspace (worktree and branch)
- If BRANCH is not a tracked workspace, commands MUST show an error with a
  suggestion to delete using git CLI
- If workspace is dirty or branch is ahead of remote, commands MUST block
  deletion unless `--force` is provided
- If no upstream is configured, commands MUST block deletion unless `--force`
  is provided
- `--force` MAY proceed even when no upstream is configured
- If BRANCH is the currently checked out workspace, commands MUST error and
  suggest switching to a safe workspace before deleting
- `--dry-run --json` MUST output a machine-readable plan without side effects

### Prune

```
$ gitcuttle prune [--dry-run] [--json] [--force]
```

- Commands MUST delete tracked workspaces when either:
  - Their PR is merged (to any target branch) on that branch's tracked remote
  - The local branch no longer exists (for example, deleted manually via git CLI)
- If workspace is dirty or branch is ahead of remote, commands MUST block
  deletion unless `--force` is provided
- If no upstream is configured, commands MUST block deletion unless `--force`
  is provided
- `--force` MAY proceed even when no upstream is configured
- When pruning a missing local branch, commands MUST remove both metadata and
  the workspace worktree directory
- If PR status is unknown/unavailable, commands MUST treat PR state as
  not-merged for pruning decisions
- `--dry-run --json` MUST output a machine-readable plan without side effects

### Updating a branch

```
$ gitcuttle update
```

- For non-octopus branches, if the current branch has an upstream, commands
  MUST rebase the current branch onto its upstream remote branch.
- For octopus branches, commands MUST rebuild from updated parents and MUST NOT
  rebase the current octopus branch onto its own upstream.
- For octopus branches, commands MUST:
  - Individually update each parent branch:
    - If parent has upstream, commands MUST rebase onto upstream
    - If parent has no upstream, commands MUST use the latest local parent
      branch tip
  - Commands MUST do a new n-way merge
  - Commands MUST cherry-pick original post-merge commits
- If current branch has no upstream, commands MUST:
  - For octopus branches, proceed using parent branch update rules above
  - Otherwise, show an error with a hint to set upstream

### Absorbing a change (octopus branch)

```
$ gitcuttle absorb [BRANCH] [-i]
```

- If not on octopus workspace, commands MUST show an error
- If BRANCH is given, commands MUST rebase post-merge commits onto branch and
  rebase the octopus merge
- If `-i` is given, commands MUST have the user interactively select a branch
  for each post-merge commit
- If no args are given, commands MUST attempt heuristic mapping of each commit
  to a parent branch based on edited files. If confidence is insufficient,
  commands MUST show an error and suggest doing interactively.
- If a commit maps to multiple possible parent branches, commands MUST treat it
  as ambiguous, fail, and require `-i`

## Testing Scope

Integration tests MUST cover user-visible CLI behavior and command contracts in
this document. Internal implementation details MAY be covered by unit tests
where appropriate.
