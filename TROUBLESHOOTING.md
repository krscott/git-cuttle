# Troubleshooting

This guide covers user-visible blocked states in the currently shipped CLI.

## Fast Triage

When a command fails:

1. Read the full error text first; it includes the blocked precondition and
   hints.
2. Confirm current git state:

```bash
git status
git rev-parse --show-toplevel
```

## Common Blocked States

### Not inside a git repo

Symptom:

```text
error[not-in-git-repo]: gitcuttle must be run from within a git repository
```

Recovery:

- `cd` to the repository root or one of its worktrees.
- Verify with `git rev-parse --show-toplevel`.

### Merge/rebase/cherry-pick in progress

Symptom:

```text
error[git-operation-in-progress]: repository has an in-progress git operation
details: detected state marker: <MARKER>
```

Recovery:

```bash
git status
git merge --abort || true
git rebase --abort || true
git cherry-pick --abort || true
```

If abort is not possible, finish the in-progress operation manually, then rerun
`gitcuttle`.

### Invalid CLI arguments

Symptom:

```text
error[invalid-arguments]: invalid command arguments
details: unrecognized arguments: <flag>
hint: run `gitcuttle --help` to view valid usage
```

Recovery:

- Check usage with `gitcuttle --help`.
- Fix the command and rerun.

## Validation Checklist After Recovery

- `git status` reflects the state you expect.
- `gitcuttle` runs without blocked-state errors.
