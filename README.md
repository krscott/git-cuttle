# git-cuttle

`git-cuttle` is a CLI for managing multi-branch git workspaces.

A workspace is a branch that contains an n-way merge of parent branches, plus
optional post-merge commits where you continue work.

## Commands

- `gitcuttle new <branch1> <branch2> ... [--name NAME]`
  - Create a new workspace branch and perform an octopus merge.
- `gitcuttle worktree <branch1> [--print-path]`
  - Create a tracked worktree for a branch under XDG data.
  - If the branch does not exist locally, git-cuttle tries matching remotes and
    prefers `origin/<branch>`.
- `gitcuttle worktree <branch1> <branch2> ... [--name NAME] [--print-path]`
  - Create a workspace branch (same as `new`) and create a tracked worktree for
    that workspace branch.
- `gitcuttle absorb [--continue]`
  - Recompute the parent merge and rebase post-merge commits onto it.
- `gitcuttle update [--continue]`
  - Pull each parent branch from remote then run `absorb`.
- `gitcuttle list`
  - List tracked workspaces and tracked single-branch worktrees.
- `gitcuttle delete [workspace]`
  - Delete tracked metadata and remove managed worktree paths for the current
    branch or named workspace/branch.
- `gitcuttle status`
  - Show status for the current tracked workspace or tracked branch worktree.

### Shell wrapper for `cd`

`gitcuttle` cannot change your parent shell directory directly. Use
`--print-path` and wrap it in a shell function:

```bash
gwt() {
  local path
  path="$(gitcuttle worktree "$@" --print-path)" || return
  [ -n "$path" ] || { echo "empty path from gitcuttle" >&2; return 1; }
  cd "$path"
}
```

Failure semantics for `--print-path`:

- success: stdout contains only the absolute path and exit code is `0`
- failure: stdout is empty, error is printed to stderr, exit code is non-zero

## Metadata

- Workspace refs are stored under `.git/refs/gitcuttle/<workspace-name>`.
- Workspace config is stored under `.git/gitcuttle/workspaces/<workspace-name>.json`.
- Tracked worktree config is stored under
  `.git/gitcuttle/tracked-worktrees/<branch-hash>.json`.
- Interrupted rebase state is stored in `.git/gitcuttle-rebase.json`.
- Managed worktree directories are stored under
  `${XDG_DATA_HOME:-~/.local/share}/gitcuttle/worktrees/<repo>/<repo-fingerprint>/<branch...>`.

## Development

```bash
nix develop
python -m pyright
python -m mypy .
python -m pytest
./format.sh
```
