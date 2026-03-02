# Design Document

This document outlines the design, architecture, and components of the
`git-cuttle` application. It serves as a comprehensive guide for understanding
and reproducing the system's functionality.

## Overview

`git-cuttle` is a Command Line Interface (CLI) application for managing git
multi-branch workflows.

## Design Methodology

In descending order, this project optimizes for:

1. Correctness - ops shall result in a good state
2. Reliability - ops should be reproducible
3. User-friendly - ops should have a minimal interface and useful error messages
4. Speed - ops should be efficient

User-visible requirements listed in this document shall have corresponding
integration tests. Wherever possible, tests should be implemented first
(Red-Green-Refactor).

## Architecture

The application is divided into distinct modules

- CLI (`__main__.py`): Handles CLI input
- Orchestrator: Connects other modules
- Git ops: Wraps the git/gh cli tools in python wrapper functions
- Metadata manager: Manages persistent metadata of all managed workspaces

## Persistent Data

All user data is stored in `$XDG_DATA_HOME/gitcuttle/workspaces.json`.

The schema shall be versioned with a `"version": int` key.

When the schema version changes, the app shall auto-migrate data to the latest
version and create a timestamped backup before writing.

This data may become outdated between invocations, so must be updated before
making filesystem changes.

## Command Scope and Tracking

- Mutating commands (`new`, `delete`, `prune`, `update`, `absorb`) shall ensure
  the current repo is tracked in `workspaces.json`.
- Read-only commands (for example, `list`) shall not create tracking entries.
- If `gitcuttle` is run outside a git repo, it shall exit with a clear error and
  guidance to run from within a git repository.

## Definitions

- workspace: A git workspace, either the original repo or a worktree dir
- octopus: A branch that is on top of an n-way merge

## Changing Directory

It is not possible to `cd` from python. For commands that "change directory":
- Never change the user's shell directory from within `gitcuttle`.
- By default, output instructions for changing directory or setting up an alias
- Accept a `--destination` flag, output only the directory to stdout, to be
  used by user aliases or bash functions

## Merge strategy

Only allow clean merge/rebase/cherry-pick. If an operation results in a git
conflict, show an error message with a suggestion on how to get git into a
state that would allow the operation.

Operations that touch multiple branches/worktrees must be atomic. If a failure
occurs, roll back all touched branches, worktrees, and metadata to their
pre-command state.

## Use Cases

In all cases, when a command is executed:

- Commands should work the same regardless if run from original repo dir
  or from worktree dir
- All short flags should also have long flags (e.g. `-b,--branch`)

### Creating a new branch and worktree

```
$ gitcuttle new [BRANCH] [-b NAME]
```

- Creates a new branch and worktree in `$XDG_DATA_HOME/gitcuttle/<repo>/<branch>`
- `BRANCH` is the base branch/commit. If not provided, use current commit as the base
- `-b, --branch NAME` is the new branch name to create
- If BRANCH is given but does not exist, show an error message, suggest 
  `new -b NAME` (no BRANCH)
- Branch name is provided with `-b NAME` or generated using a random inverse 
  hex (e.g. `workspace-zyxwvut`)
  - If given branch name contains `/`, it should be sanitized in the dir name,
    but kept in the git branch name. The sanitization mapping must be stable.
- If branch already exists locally or on its tracked remote, then show an error message
- Print destination path/instructions; do not attempt to change the caller's cwd

#### Creating an octopus branch

```
$ gitcuttle new BRANCH [BRANCH...] [-b NAME]
```

- Create a new workspace and branch that is an n-way (octopus) merge with
  given branches
- Track all bases in `workspaces.json`
- Preserve and persist parent branch order exactly as provided

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
show unknown/blank markers and continue.

### Delete workspace

```
$ gitcuttle delete BRANCH [--dry-run] [--force]
```

- Delete the tracked BRANCH workspace (worktree and branch)
- If BRANCH is not a tracked workspace show an error message with a suggestion
  to delete using git cli
- If workspace is dirty or branch is ahead of remote, block deletion unless
  `--force` is provided

### Prune

```
$ gitcuttle prune [--dry-run] [--force]
```

- Delete tracked workspaces when either:
  - Their PR is merged (to any target branch) on that branch's tracked remote
  - The local branch no longer exists (for example, deleted manually via git cli)
- If workspace is dirty or branch is ahead of remote, block deletion unless
  `--force` is provided
- When pruning a missing local branch, remove both metadata and the workspace
  worktree directory

### Updating a branch

```
$ gitcuttle update
```

- Rebase current branch onto the remote branch
- Handle octopus branches:
  - Individually update each parent branch:
    - If parent has upstream, rebase onto upstream
    - If parent has no upstream, use latest local parent branch tip
  - Do a new n-way merge
  - Cherry-pick original post-merge commits
- If current branch has no upstream:
  - For octopus branches, proceed using parent branch update rules above
  - Otherwise, show an error with a hint to set upstream

### Absorbing a change (octopus branch)

```
$ gitcuttle absorb [BRANCH] [-i]
```

- If not on octopus workspace, show an error
- If BRANCH is given, rebase post-merge commits onto branch and rebase the
  octopus merge
- If `-i` is given, have user interactively select a branch for each
  post-merge commit
- If no args given, heuristically determine which branch each commit should go
  based on the branches' edited files. If not possible to do reliably, show
  an error and suggest doing interactively.
- If a commit maps to multiple possible parent branches, treat as ambiguous,
  fail, and require `-i`

## Testing Scope

Integration tests are required for user-visible CLI behavior and command
contracts in this document. Internal implementation details may be covered by
unit tests where appropriate.
