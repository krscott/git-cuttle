# Design Document

## Overview

`git-cuttle` provides a git-style CLI for building and maintaining multi-branch
workspaces. A workspace is a branch created from an n-way merge of parent
branches. Users can do post-merge work on that workspace branch, then later
refresh the merge and rebase post-merge commits onto the refreshed result.

## Architecture

1. **CLI layer** (`git_cuttle/cli.py`, `git_cuttle/__main__.py`)
   - Parses subcommands and arguments.
   - Performs user-facing error handling.
2. **Git operations layer** (`git_cuttle/git_ops.py`)
   - Thin, typed wrappers around `git` subprocess commands.
3. **Workspace metadata layer** (`git_cuttle/workspace.py`)
   - Immutable `WorkspaceConfig` model.
   - Persistence and retrieval of workspace metadata.
4. **Rebase orchestration layer** (`git_cuttle/rebase.py`)
   - Recomputes merge commit and rebases workspace commits.
   - Stores and restores interrupted rebase state.

## Data Model

- `WorkspaceConfig`
  - `name`: workspace id.
  - `branches`: parent branches included in the merge.
  - `base_branch`: branch from which workspace was created.
  - `merge_branch`: workspace branch name.
- `RebaseState`
  - `operation`: `"rebase"` or `"pull"`.
  - `workspace_name`: workspace identifier.
  - `original_head`: merge commit before refresh.
  - `target_branch`: refreshed merge commit.

## Persistence

- Workspace ref: `.git/refs/gitcuttle/<workspace-name>` (points to merge commit).
- Workspace config: `.git/gitcuttle/workspaces/<workspace-name>.json`.
- Rebase resume state: `.git/gitcuttle-rebase.json`.

## Command Behavior

- `gitcuttle new <branch...> [--name]`
  - Creates a workspace branch and performs octopus merge of parents.
  - Persists metadata and merge ref.
- `gitcuttle absorb [--continue]`
  - Recomputes parent merge on a temporary branch.
  - Rebases post-merge commits onto refreshed merge.
- `gitcuttle update [--continue]`
  - Pulls each parent branch (`git pull --ff-only`) then runs absorb flow.
- `gitcuttle list`
  - Lists all persisted workspaces.
- `gitcuttle delete [workspace]`
  - Removes workspace metadata/ref tracking without deleting git branches.
- `gitcuttle status`
  - Shows current workspace and post-merge commit count.

## Data Flow

1. User runs a subcommand through `gitcuttle`.
2. CLI resolves current workspace from current git branch when needed.
3. Git layer runs required plumbing/porcelain operations.
4. Workspace metadata is read/written under `.git` namespaces.
5. For `absorb`/`update`, interrupted rebases persist state for `--continue`.
