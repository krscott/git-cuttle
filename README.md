# git-cuttle

`git-cuttle` currently ships a subcommand-oriented CLI that runs inside an
existing git repository.

## Command behavior

- `gitcuttle new -b <branch> [base ...]` creates a new tracked workspace.
- `gitcuttle list` shows tracked workspaces and remote/PR status.
- `gitcuttle delete`, `gitcuttle prune`, `gitcuttle update`, and
  `gitcuttle absorb` execute workflow operations.
- `gitcuttle --verbose` (or `-v`, or `GITCUTTLE_VERBOSE=1`) enables debug logs.

## Quick examples

Create a workspace:

```bash
gitcuttle new -b feature/demo
```

```text
created workspace 'feature/demo' at /tmp/.../feature-demo
hint: cd /tmp/.../feature-demo
```

Path-only output for shell navigation helpers:

```bash
gitcuttle new -b feature/demo --destination
```

```text
/tmp/.../feature-demo
```

List invocation:

```bash
gitcuttle list
```

```text
REPO  BRANCH  DIRTY  AHEAD  BEHIND  PR  DESCRIPTION  WORKTREE
(no tracked workspaces)
```

Dry-run delete plan:

```bash
gitcuttle delete feature/demo --dry-run
```

```text
Dry-run plan for `delete`:
1. delete-worktree: /tmp/.../feature-demo
2. delete-branch: feature/demo
3. untrack-workspace: feature/demo
```

## Blocked states and troubleshooting

The CLI blocks when preconditions are not met, and returns actionable guidance.

Outside a git repo:

```text
error[not-in-git-repo]: gitcuttle must be run from within a git repository
hint: change to your repository root or one of its worktrees and retry
```

Git operation in progress:

```text
error[git-operation-in-progress]: repository has an in-progress git operation
details: detected state marker: MERGE_HEAD
hint: resolve or abort the git operation and rerun gitcuttle
```

Invalid arguments:

```text
error[invalid-arguments]: invalid command arguments
hint: run `gitcuttle --help` to view valid usage
```

For recovery steps and git-state triage commands, see
[`TROUBLESHOOTING.md`](TROUBLESHOOTING.md).

## Related docs

- [`DESIGN.md`](DESIGN.md): target architecture and delivery plan
- [`TROUBLESHOOTING.md`](TROUBLESHOOTING.md): blocked-state recovery and triage
- [`INTEGRATION_TEST_MATRIX.md`](INTEGRATION_TEST_MATRIX.md): behavior coverage
