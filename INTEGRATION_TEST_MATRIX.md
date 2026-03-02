# Integration Test Matrix

This matrix maps user-visible requirements from `DESIGN.md` to integration test
coverage. It is the contract checklist for black-box CLI behavior.

Status values:

- `covered`: Existing integration test asserts this behavior.
- `planned`: Required by `DESIGN.md`, test not yet implemented.

## Global CLI behavior

| Requirement | DESIGN.md reference | Status | Test reference / plan |
|---|---|---|---|
| Command succeeds with default invocation path | `DESIGN.md:182` | covered | `tests/test_integration.py::test_cli_default_name` |
| Verbose mode via `--verbose` | `DESIGN.md:186` | covered | `tests/test_integration.py::test_cli_verbose_flag` |
| Verbose mode via `-v` | `DESIGN.md:186` | covered | `tests/test_integration.py::test_cli_verbose_short_flag` |
| Env var controls verbose mode | CLI env contract | covered | `tests/test_integration.py::test_cli_verbose_env_var` |
| Flag behavior independent of env var defaults | CLI env contract | covered | `tests/test_integration.py::test_cli_flag_overrides_env_var` |
| Hard error outside git repository with guidance | `DESIGN.md:134` | covered | `tests/test_integration.py::test_cli_errors_outside_git_repo` |
| Behavior is identical from repo root and worktree | `DESIGN.md:184` | covered | `tests/test_integration.py::test_cli_behaves_same_from_repo_root_and_worktree` |

## Navigation output contract

| Requirement | DESIGN.md reference | Status | Test reference / plan |
|---|---|---|---|
| `--destination` prints destination path only to stdout | `DESIGN.md:148` | covered | `tests/test_integration.py::test_cli_destination_outputs_path_only` |
| `-d` short flag matches `--destination` behavior | `DESIGN.md:151` | covered | `tests/test_integration.py::test_cli_destination_short_flag_outputs_path_only` |

## Workspace command contracts

| Command flow | Requirement | DESIGN.md reference | Status | Planned coverage |
|---|---|---|---|---|
| `new` standard | Base resolution, branch create, sanitized destination path, branch conflict errors | `DESIGN.md:188` | planned | Add integration cases for base provided/missing, existing local/remote branch, deterministic path mapping |
| `new` octopus | N-way merge creation and ordered parent persistence | `DESIGN.md:214` | planned | Add integration cases asserting parent order and persisted metadata |
| `list` | Table columns and graceful unknown markers for remote/PR failures | `DESIGN.md:225` | planned | Add integration cases for offline/unauthenticated states with non-fatal output |
| `delete` | Safety gates (`dirty`, ahead, no-upstream), current-workspace block, force and dry-run/json plans | `DESIGN.md:242` | planned | Add integration cases for each block and force override |
| `prune` | Merged-PR or missing-local-branch criteria, unknown PR treated as not merged, force and dry-run/json plans | `DESIGN.md:260` | planned | Add integration cases for each prune reason and unknown PR behavior |
| `update` non-octopus | Upstream rebase path and no-upstream error | `DESIGN.md:280` | planned | Add integration cases for upstream present/absent |
| `update` octopus | Parent updates, new n-way merge, replay post-merge commits | `DESIGN.md:288` | planned | Add integration cases validating merge parent order and replayed commits |
| `absorb` | Explicit target branch, interactive mode, heuristic ambiguity failure path | `DESIGN.md:301` | planned | Add integration cases for explicit, interactive, and ambiguous heuristic flows |

## Safety, transactions, and rollback

| Requirement | DESIGN.md reference | Status | Planned coverage |
|---|---|---|---|
| Clean-operation policy: no conflict-accepting merge/rebase/cherry-pick flows | `DESIGN.md:156` | planned | Build conflict fixtures and assert blocking guidance |
| Atomic multi-branch/worktree operations | `DESIGN.md:161` | planned | Inject failures mid-operation and assert full rollback |
| Backup refs under `refs/gitcuttle/txn/<txn-id>/...` for touched branches | `DESIGN.md:172` | planned | Assert temporary refs exist during txn and are cleaned on success |
| Rollback failure reports exact partial state and deterministic recovery commands | `DESIGN.md:165` | planned | Force rollback failure and assert required recovery output |

## Metadata and tracking contracts

| Requirement | DESIGN.md reference | Status | Test reference / plan |
|---|---|---|---|
| `workspaces.json` schema v1 validation and invariants | `DESIGN.md:58` | covered | `tests/test_metadata_manager.py` |
| Canonical repo identity keyed by git dir realpath | `DESIGN.md:96` | covered | `tests/test_metadata_manager.py` |
| Atomic metadata writes | `DESIGN.md:174` | covered | `tests/test_metadata_manager.py` |
| Schema migration creates backup before write | `DESIGN.md:49` | covered | `tests/test_metadata_manager.py` |
| Workspace path derivation and deterministic collision handling | `DESIGN.md:115` | covered | `tests/test_workspace_paths.py` |
| Mutating commands auto-track repo; read-only commands do not create tracking entries | `DESIGN.md:131` | planned | Add integration cases for `new/delete/prune/update/absorb` vs `list` |

## Remote and cache contracts

| Requirement | DESIGN.md reference | Status | Planned coverage |
|---|---|---|---|
| `list` uses short TTL status cache (default 60s) | `DESIGN.md:112` | planned | Add integration cases with clock control/fake backend |
| Cache refresh does not create tracking entries | `DESIGN.md:113` | planned | Add integration case invoking `list` in untracked repo |
| Prune treats unknown PR status as not merged | `DESIGN.md:276` | planned | Add integration case with unavailable PR provider |
