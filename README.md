# git-cuttle

`git-cuttle` is a CLI for managing multi-branch git workspaces.

A workspace is a branch that contains an n-way merge of parent branches, plus
optional post-merge commits where you continue work.

## Commands

- `gitcuttle new <branch1> <branch2> ... [--name NAME]`
  - Create a new workspace branch and perform an octopus merge.
- `gitcuttle absorb [--continue]`
  - Recompute the parent merge and rebase post-merge commits onto it.
- `gitcuttle update [--continue]`
  - Pull each parent branch from remote then run `absorb`.
- `gitcuttle list`
  - List tracked workspaces.
- `gitcuttle delete [workspace]`
  - Delete persisted workspace metadata for the current (or named) workspace.
- `gitcuttle status`
  - Show status for the current workspace branch.

## Metadata

- Workspace refs are stored under `.git/refs/gitcuttle/<workspace-name>`.
- Workspace config is stored under `.git/gitcuttle/workspaces/<workspace-name>.json`.
- Interrupted rebase state is stored in `.git/gitcuttle-rebase.json`.

## Development

```bash
nix develop
python -m pyright
python -m mypy .
python -m pytest
./format.sh
```
