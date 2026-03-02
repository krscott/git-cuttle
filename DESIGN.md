# Design Document

## Overview

`git-cuttle` provides a git-style CLI for building and maintaining multi-branch
workspaces. A workspace is a branch created from an n-way merge of parent
branches. Users can do post-merge work on that workspace branch, then later
refresh the merge and rebase post-merge commits onto the refreshed result.

## Design Priorities

In descending order, this project optimizes for:

1. Correctness
2. Reliability
3. Convenience
4. Speed

## Architecture

1. **CLI layer** (`git_cuttle/cli.py`, `git_cuttle/__main__.py`)
   - Parses subcommands and arguments.
   - Performs user-facing error handling.
2. **Git operations layer** (`git_cuttle/git_ops.py`)
    - Thin, typed wrappers around `git` subprocess commands.
3. **Workspace metadata layer** (`git_cuttle/workspace.py`)
    - Immutable `WorkspaceConfig` model.
    - Persistence and retrieval of workspace metadata.
4. **Worktree tracking layer** (`git_cuttle/worktree_tracking.py`)
   - Creates managed worktree paths under XDG data home.
   - Persists tracked worktree metadata under `.git/gitcuttle`.
   - Resolves local and remote branch targets for worktree creation.
5. **Rebase orchestration layer** (`git_cuttle/rebase.py`)
    - Recomputes merge commit and rebases workspace commits.
    - Stores and restores interrupted rebase state.

## Data Model

- `WorkspaceConfig`
  - `name`: workspace id.
  - `branches`: parent branches included in the merge.
  - `base_branch`: branch from which workspace was created.
  - `merge_branch`: workspace branch name.
- `TrackedWorktree`
  - `branch`: branch name associated with the managed worktree.
  - `path`: absolute managed worktree path.
  - `kind`: either `"branch"` (single-branch mode) or `"workspace"`.
  - `workspace_name`: optional workspace id when `kind == "workspace"`.
- `RebaseState`
  - `operation`: `"rebase"` or `"pull"`.
  - `workspace_name`: workspace identifier.
  - `original_head`: merge commit before refresh.
  - `target_branch`: refreshed merge commit.

## Persistence

- Workspace ref: `.git/refs/gitcuttle/<workspace-name>` (points to merge commit).
- Workspace config: `.git/gitcuttle/workspaces/<workspace-name>.json`.
- Tracked worktree config: `.git/gitcuttle/tracked-worktrees/<branch-hash>.json`.
- Managed worktree directories:
  `${XDG_DATA_HOME:-~/.local/share}/gitcuttle/worktrees/<repo>/<repo-fingerprint>/<branch...>`.
- Rebase resume state: `.git/gitcuttle-rebase.json`.

## Command Behavior

- `gitcuttle new <branch...> [--name]`
  - Creates a workspace branch and performs octopus merge of parents.
  - Persists metadata and merge ref.
- `gitcuttle worktree <branch...> [--name] [--print-path]`
  - Single branch: creates/reuses a managed tracked worktree for the branch.
  - If local branch is missing, resolves remote branch (prefers `origin`).
  - Multiple branches: runs workspace creation flow then adds tracked worktree.
  - `--print-path` prints only the resulting absolute path on success.
  - On failure in `--print-path` mode, stdout remains empty and errors go to stderr.
- `gitcuttle absorb [--continue]`
  - Recomputes parent merge on a temporary branch.
  - Rebases post-merge commits onto refreshed merge.
- `gitcuttle update [--continue]`
  - Pulls each parent branch (`git pull --ff-only`) then runs absorb flow.
- `gitcuttle list`
  - Lists persisted workspaces and tracked single-branch worktrees.
- `gitcuttle delete [workspace-or-branch]`
  - Removes tracked worktree path and tracked metadata when present.
  - Removes workspace metadata/ref when target is a workspace.
  - Supports `--workspace-only` and `--worktree-only` for explicit targeting.
  - If both targets exist but are not the same tracked workspace pair, delete
    fails with an ambiguity error and requires explicit targeting.
- `gitcuttle status`
  - Shows current tracked workspace or tracked branch worktree state.

## Data Flow

1. User runs a subcommand through `gitcuttle`.
2. CLI resolves current workspace from current git branch when needed.
3. Git layer runs required plumbing/porcelain operations.
4. Worktree command computes managed path under XDG data and runs `git worktree`.
5. Workspace and tracked worktree metadata is read/written under `.git` namespaces.
6. For `absorb`/`update`, interrupted rebases persist state for `--continue`.
