# git-cuttle

`git-cuttle` is a CLI for managing multi-branch git workspace workflows with
safe, predictable operations.

## Command overview

`git-cuttle` is designed around a small set of flows:

- `new`: create a tracked branch + workspace
- `list`: inspect tracked workspaces and status
- `update`: pull in upstream changes
- `absorb`: move octopus post-merge commits back to parent branches
- `delete`: remove a tracked workspace
- `prune`: clean up workspaces that are merged or otherwise removable

For normative behavior details and edge-case contracts, see
[`DESIGN.md`](DESIGN.md).

## Quick examples

Create a workspace from your current commit:

```bash
gitcuttle new -b feature/login
```

Create an octopus workspace from multiple parent branches:

```bash
gitcuttle new main release/hotfix -b integration/main-hotfix
```

List tracked workspaces:

```bash
gitcuttle list
```

Delete a tracked workspace:

```bash
gitcuttle delete feature/login
```

Preview prune actions without side effects:

```bash
gitcuttle prune --dry-run
gitcuttle prune --dry-run --json
```

Update the current workspace:

```bash
gitcuttle update
```

Absorb octopus post-merge commits:

```bash
gitcuttle absorb
gitcuttle absorb parent-branch
gitcuttle absorb -i
```

## Major flow details

### 1) Create (`new`)

- Creates a branch and workspace under `$XDG_DATA_HOME/gitcuttle/<repo-id>/<branch-dir>`.
- Supports standard and octopus creation flows.
- Preserves original branch names in metadata even when filesystem path names
  are sanitized.

```bash
gitcuttle new [BASE] -b <branch-name>
gitcuttle new <parent-1> <parent-2> [parent-N...] -b <octopus-branch>
```

### 2) Inspect (`list`)

- Shows tracked workspaces with local status and remote/PR context.
- Degrades gracefully when remote/PR data is unavailable.

```bash
gitcuttle list
```

### 3) Update (`update`)

- Non-octopus workspaces rebase onto upstream when configured.
- Octopus workspaces rebuild from parent branches and replay post-merge commits.

```bash
gitcuttle update
```

### 4) Absorb (`absorb`)

- Octopus-only flow to move post-merge commits onto parent branches.
- Supports explicit target mode, heuristic mode, and interactive selection.

```bash
gitcuttle absorb [parent-branch] [-i]
```

### 5) Remove (`delete`, `prune`)

- `delete` removes one tracked workspace branch/worktree.
- `prune` removes workspaces that are merged or no longer have a local branch.
- Both support safety gates, force mode, and dry-run planning output.

```bash
gitcuttle delete <branch> [--force] [--dry-run] [--json]
gitcuttle prune [--force] [--dry-run] [--json]
```

## Navigation-friendly output

Commands that conceptually navigate to a workspace path support
`-d, --destination`, which prints path-only output for shell aliases/functions.

```bash
gitcuttle --destination
```

## Related docs

- [`DESIGN.md`](DESIGN.md): strict behavior and command contracts
- [`TROUBLESHOOTING.md`](TROUBLESHOOTING.md): rollback and git-state recovery
- [`INTEGRATION_TEST_MATRIX.md`](INTEGRATION_TEST_MATRIX.md): user-visible
  behavior coverage
