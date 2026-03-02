# Troubleshooting

This guide covers operational recovery for `git-cuttle` workflows, with a focus
on rollback and common git-state blockers.

## Fast Triage

When a command fails:

1. Read the full error text first; it should include the blocked precondition.
2. Confirm current git state:

```bash
git status
git branch --show-current
git rev-parse --show-toplevel
```

3. If you were in a multi-step operation, check for temporary transaction refs:

```bash
git for-each-ref --format='%(refname)' refs/gitcuttle/txn
```

4. Do not run destructive cleanup (`git reset --hard`, `git clean -fd`) until
   you have captured the current state.

## Common Blocked States

### Not inside a git repo

Symptom: command exits with a repo-context error.

Recovery:

- `cd` to the repository root or any worktree for that repository.
- Verify with `git rev-parse --show-toplevel`.

### Merge/rebase/cherry-pick in progress

Symptom: command refuses to proceed because the repo is not in a clean
operation state.

Recovery:

```bash
git status
git merge --abort || true
git rebase --abort || true
git cherry-pick --abort || true
```

If abort is not possible, finish the in-progress operation manually, then rerun
the `gitcuttle` command.

### Dirty working tree or safety gate block

Symptom: delete/prune/update-style operation is blocked for safety.

Recovery options:

- Commit the changes and rerun.
- Stash the changes (`git stash push -u`) and rerun.
- Use the command's force mode only when you have verified that data loss is
  acceptable.

### No upstream configured

Symptom: operation that requires remote comparison or rebase is blocked.

Recovery:

```bash
git branch --set-upstream-to origin/<branch> <branch>
```

Then rerun the original command.

## Rollback Recovery

For transactional operations, `git-cuttle` may create temporary backup refs
under:

`refs/gitcuttle/txn/<txn-id>/...`

If rollback succeeds, these refs should be removed automatically. If rollback
fails, use this process.

### 1) Inspect backup refs

```bash
git for-each-ref --format='%(refname) %(objectname)' refs/gitcuttle/txn
```

### 2) Restore affected branches

For each affected branch, reset the branch ref to the backup commit:

```bash
git update-ref refs/heads/<branch> <backup-commit-sha>
```

### 3) Reconcile worktrees

List worktrees and remove stale entries/dirs:

```bash
git worktree list
git worktree remove <path>
git worktree prune
```

### 4) Reconcile metadata

Restore metadata from the latest backup file before migration/write:

`$XDG_DATA_HOME/gitcuttle/workspaces.json.bak.<unix-timestamp>`

Then verify the active file:

`$XDG_DATA_HOME/gitcuttle/workspaces.json`

### 5) Remove transaction refs after validation

After confirming branches, worktrees, and metadata are consistent:

```bash
git for-each-ref --format='delete %(refname)' refs/gitcuttle/txn | git update-ref --stdin
```

## Validation Checklist After Recovery

- `git status` is clean (or intentionally dirty).
- `git worktree list` matches expected workspace directories.
- Expected branches point to expected commits.
- `workspaces.json` entries match existing branches/worktrees.

## When to Escalate

Escalate to manual review (or pair with another developer) when:

- A branch tip is unknown and no backup ref exists.
- Metadata and git state disagree for multiple workspaces.
- You cannot identify whether an operation already partially applied.

Capture and share:

- `git status`
- `git worktree list`
- `git for-each-ref --format='%(refname) %(objectname)' refs/gitcuttle/txn`
- Relevant metadata file and backup filenames
