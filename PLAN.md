## Worktree Tracking Feature Plan

### Goals
- Add a new `worktree` command that creates git worktrees under git-cuttle managed XDG data paths.
- Support both single-branch worktree creation and multi-branch workspace+worktree creation.
- Track managed worktrees in git-cuttle metadata.
- Provide machine-friendly path output for shell wrappers via `--print-path`.

### Confirmed Behavior
- Command shape: `gitcuttle worktree <branch...> [--name NAME] [--print-path]`
- Single branch:
  - Equivalent to `git worktree add <path> <branch>`.
  - If local branch is missing, resolve remote branch by preferring `origin/<branch>`.
  - If remote match is ambiguous or missing, fail clearly.
- Multiple branches:
  - Reuse existing `new` semantics to create a tracked workspace branch.
  - Then create a managed worktree for that workspace branch.
- Worktree location:
  - Root under `XDG_DATA_HOME` (fallback `~/.local/share`).
  - Include visible `repo/branch` in the path.
  - Avoid collisions between same-named repos by including a stable repo fingerprint.
- Existing target path:
  - If already the correct worktree, reuse and succeed.
- `--print-path`:
  - Success: print only absolute path on stdout.
  - Failure: print nothing on stdout, write error to stderr, exit non-zero.
- `list` and `status`:
  - Include both workspace-tracked entries and single-branch tracked worktrees.
- `delete`:
  - Remove managed worktree path and associated metadata.
  - For workspace entries, also remove workspace metadata/ref.

### Implementation Steps
1. Add worktree tracking data model and persistence layer.
2. Add git helpers for branch and worktree operations.
3. Implement XDG path resolution and target path generation.
4. Add `worktree` CLI command and `--print-path` behavior.
5. Extend `list`/`status`/`delete` to include tracked worktrees.
6. Add/adjust tests for command behavior and failure semantics.
7. Update `README.md` with command docs and safe shell wrapper examples.
8. Update `DESIGN.md` for architecture and data flow changes.
9. Run `python -m pyright`, `python -m mypy .`, `python -m pytest`, `nix flake show '.?submodules=1'`, and `./format.sh`.

### Commit Plan
- Commit 1: Add `PLAN.md` and initial structural changes.
- Commit 2: Implement core worktree command behavior and metadata tracking.
- Commit 3: Complete tests and docs updates, then run full verification.
