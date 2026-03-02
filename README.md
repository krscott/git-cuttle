# git-cuttle

`git-cuttle` currently ships a minimal CLI surface that runs inside an existing
git repository.

## Command behavior

- `gitcuttle [name]` prints `Hello, <name>!` (default name: `World`).
- `gitcuttle --destination` (or `-d`) prints the absolute path of the current
  working directory and exits.
- `gitcuttle --verbose` (or `-v`, or `GITCUTTLE_VERBOSE=1`) enables debug logs.

## Quick examples

Basic greeting:

```bash
gitcuttle Alice
```

```text
Hello, Alice!
```

Default greeting:

```bash
gitcuttle
```

```text
Hello, World!
```

Path-only output for shell navigation helpers:

```bash
gitcuttle --destination
```

```text
/absolute/path/to/current/directory
```

Verbose logging:

```bash
gitcuttle --verbose Bob
```

```text
Hello, Bob!
# stderr also includes: Greeting user...
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
