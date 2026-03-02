# git-cuttle

`git-cuttle` currently ships a subcommand-oriented CLI that runs inside an
existing git repository.

## Command behavior

- `gitcuttle new -b <branch> [base ...]` creates a new workspace invocation path.
- `gitcuttle list`, `gitcuttle delete`, `gitcuttle prune`, `gitcuttle update`,
  and `gitcuttle absorb` are available subcommands.
- `gitcuttle --verbose` (or `-v`, or `GITCUTTLE_VERBOSE=1`) enables debug logs.

## Quick examples

Create a workspace command invocation:

```bash
gitcuttle new -b feature/demo
```

```text
created workspace 'feature/readme' at /tmp/.../feature-readme
hint: cd /tmp/.../feature-readme
```

Path-only output for shell navigation helpers:

```bash
gitcuttle new -b feature/demo --destination
```

```text
/tmp/.../feature-readme
```

List invocation:

```bash
gitcuttle list
```

```text
list:invoked
```

Dry-run delete plan:

```bash
gitcuttle delete feature/demo --dry-run
```

```text
delete:planned
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
