# Integration Test Matrix

This matrix maps user-visible requirements from `DESIGN.md` to integration test
coverage. It is the contract checklist for black-box CLI behavior.
References use `DESIGN.md` section names (not line numbers) to avoid drift.

Status values:

- `covered`: Existing integration test asserts this behavior.
- `planned`: Required by `DESIGN.md`, test not yet implemented.

## Global CLI behavior

| Requirement | DESIGN.md section | Status | Test reference / plan |
|---|---|---|---|
| Command succeeds with default invocation path | Use Cases (common execution invariants) | covered | `tests/test_integration.py::test_cli_default_name` |
| Verbose mode via `--verbose` | Architecture (CLI module) | covered | `tests/test_integration.py::test_cli_verbose_flag` |
| Verbose mode via `-v` | Architecture (CLI module) | covered | `tests/test_integration.py::test_cli_verbose_short_flag` |
| Env var controls verbose mode | Architecture (CLI module) | covered | `tests/test_integration.py::test_cli_verbose_env_var` |
| Flag behavior independent of env var defaults | Architecture (CLI module) | covered | `tests/test_integration.py::test_cli_flag_overrides_env_var` |
| Hard error outside git repository with guidance | Command Scope and Tracking | covered | `tests/test_integration.py::test_cli_errors_outside_git_repo` |
| Behavior is identical from repo root and worktree | Use Cases (common execution invariants) | covered | `tests/test_integration.py::test_cli_behaves_same_from_repo_root_and_worktree` |

## Navigation output contract

| Requirement | DESIGN.md section | Status | Test reference / plan |
|---|---|---|---|
| `--destination` prints destination path only to stdout | Changing Directory | covered | `tests/test_integration.py::test_cli_destination_outputs_path_only` |
| `-d` short flag matches `--destination` behavior | Changing Directory | covered | `tests/test_integration.py::test_cli_destination_short_flag_outputs_path_only` |

## Workspace command contracts

| Command flow | Requirement | DESIGN.md section | Status | Planned coverage |
|---|---|---|---|---|
| `new` standard | Base resolution, branch create, sanitized destination path, branch conflict errors | Use Cases -> Creating a new branch and worktree | planned | Add integration cases for base provided/missing, existing local/remote branch, deterministic path mapping |
| `new` octopus | N-way merge creation and ordered parent persistence | Use Cases -> Creating an octopus branch | planned | Add integration cases asserting parent order and persisted metadata |
| `list` | Table columns and graceful unknown markers for remote/PR failures | Use Cases -> List workspaces | planned | Add integration cases for offline/unauthenticated states with non-fatal output |
| `delete` | Safety gates (`dirty`, ahead, no-upstream), current-workspace block, force and dry-run/json plans | Use Cases -> Delete workspace | planned | Add integration cases for each block and force override |
| `prune` | Merged-PR or missing-local-branch criteria, unknown PR treated as not merged, force and dry-run/json plans | Use Cases -> Prune | planned | Add integration cases for each prune reason and unknown PR behavior |
| `update` non-octopus | Upstream rebase path and no-upstream error | Use Cases -> Updating a branch | planned | Add integration cases for upstream present/absent |
| `update` octopus | Parent updates, new n-way merge, replay post-merge commits | Use Cases -> Updating a branch | planned | Add integration cases validating merge parent order and replayed commits |
| `absorb` | Explicit target branch, interactive mode, heuristic ambiguity failure path | Use Cases -> Absorbing a change (octopus branch) | planned | Add integration cases for explicit, interactive, and ambiguous heuristic flows |

## Safety, transactions, and rollback

| Requirement | DESIGN.md section | Status | Planned coverage |
|---|---|---|---|
| Clean-operation policy: no conflict-accepting merge/rebase/cherry-pick flows | Merge strategy | planned | Build conflict fixtures and assert blocking guidance |
| Atomic multi-branch/worktree operations | Merge strategy | planned | Inject failures mid-operation and assert full rollback |
| Backup refs under `refs/gitcuttle/txn/<txn-id>/...` for touched branches | Merge strategy (minimum rollback mechanism) | planned | Assert temporary refs exist during txn and are cleaned on success |
| Rollback failure reports exact partial state and deterministic recovery commands | Merge strategy | planned | Force rollback failure and assert required recovery output |

## Metadata and tracking contracts

| Requirement | DESIGN.md section | Status | Test reference / plan |
|---|---|---|---|
| `workspaces.json` schema v1 validation and invariants | Persistent Data -> workspaces.json schema | covered | `tests/test_metadata_manager.py` |
| Canonical repo identity keyed by git dir realpath | Persistent Data -> workspaces.json schema (invariants) | covered | `tests/test_metadata_manager.py` |
| Atomic metadata writes | Merge strategy (minimum rollback mechanism) | covered | `tests/test_metadata_manager.py` |
| Schema migration creates backup before write | Persistent Data | covered | `tests/test_metadata_manager.py` |
| Workspace path derivation and deterministic collision handling | Persistent Data -> Workspace path derivation | covered | `tests/test_workspace_paths.py` |
| Mutating commands auto-track repo; read-only commands do not create tracking entries | Command Scope and Tracking | planned | Add integration cases for `new/delete/prune/update/absorb` vs `list` |

## Remote and cache contracts

| Requirement | DESIGN.md section | Status | Planned coverage |
|---|---|---|---|
| `list` uses short TTL status cache (default 60s) | Persistent Data -> Status cache | planned | Add integration cases with clock control/fake backend |
| Cache refresh does not create tracking entries | Persistent Data -> Status cache | planned | Add integration case invoking `list` in untracked repo |
| Prune treats unknown PR status as not merged | Use Cases -> Prune | planned | Add integration case with unavailable PR provider |
