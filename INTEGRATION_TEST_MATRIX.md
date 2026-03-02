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

| Command flow | Requirement | DESIGN.md section | Status | Test reference |
|---|---|---|---|---|
| `new` standard | Base resolution, branch create, sanitized destination path, branch conflict errors | Use Cases -> Creating a new branch and worktree | covered | `tests/test_new_cli_integration.py::test_cli_new_standard_from_repo_root_creates_workspace_and_metadata`; `tests/test_new_cli_integration.py::test_cli_new_rejects_branch_when_name_exists_on_default_remote`; `tests/test_new_cli_integration.py::test_cli_new_checks_branch_conflicts_locally_without_remote_context`; `tests/test_new_cli_integration.py::test_cli_new_invalid_base_ref_shows_actionable_hint` |
| `new` octopus | N-way merge creation and ordered parent persistence | Use Cases -> Creating an octopus branch | covered | `tests/test_new_cli_integration.py::test_cli_new_octopus_from_worktree_context_creates_workspace` |
| `list` | Table columns and graceful unknown markers for remote/PR failures | Use Cases -> List workspaces | covered | `tests/test_list_cli_integration.py::test_list_renders_online_github_pr_status`; `tests/test_list_cli_integration.py::test_list_shows_unknown_marker_when_gh_is_offline` |
| `delete` | Safety gates (`dirty`, ahead, no-upstream), current-workspace block, force and dry-run/json plans | Use Cases -> Delete workspace | covered | `tests/test_delete_prune_integration.py::test_delete_blocks_dirty_workspace_without_force`; `tests/test_delete_prune_integration.py::test_delete_dry_run_matches_mutating_block_without_upstream`; `tests/test_delete_prune_integration.py::test_delete_dry_run_json_outputs_plan_without_changes`; `tests/test_mutating_command_parity_cli_integration.py::test_cli_delete_has_repo_root_worktree_parity` |
| `prune` | Merged-PR or missing-local-branch criteria, unknown PR treated as not merged, force and dry-run/json plans | Use Cases -> Prune | covered | `tests/test_delete_prune_integration.py::test_prune_missing_local_branch_removes_worktree_directory_and_metadata`; `tests/test_delete_prune_integration.py::test_prune_does_not_remove_branch_for_unknown_pr_state`; `tests/test_delete_prune_integration.py::test_prune_dry_run_json_outputs_prune_plan_and_blocking_warning`; `tests/test_mutating_command_parity_cli_integration.py::test_cli_prune_has_repo_root_worktree_parity` |
| `update` non-octopus | Upstream rebase path and no-upstream error | Use Cases -> Updating a branch | covered | `tests/test_update_integration.py::test_update_non_octopus_rebases_local_commit_onto_upstream`; `tests/test_update_integration.py::test_update_non_octopus_fails_when_no_upstream_is_configured`; `tests/test_mutating_command_parity_cli_integration.py::test_cli_update_has_repo_root_worktree_parity` |
| `update` octopus | Parent updates, new n-way merge, replay post-merge commits | Use Cases -> Updating a branch | covered | `tests/test_update_integration.py::test_update_octopus_rebuilds_from_updated_parents_and_replays_post_merge_commits`; `tests/test_update_integration.py::test_update_octopus_rolls_back_branch_on_merge_failure` |
| `absorb` | Explicit target branch, interactive mode, heuristic ambiguity failure path | Use Cases -> Absorbing a change (octopus branch) | covered | `tests/test_absorb_cli_integration.py::test_cli_absorb_explicit_target_moves_commits_to_parent`; `tests/test_absorb_cli_integration.py::test_cli_absorb_interactive_mode_uses_selected_parent`; `tests/test_absorb_cli_integration.py::test_cli_absorb_heuristic_mode_reports_ambiguity`; `tests/test_mutating_command_parity_cli_integration.py::test_cli_absorb_has_repo_root_worktree_parity` |

## Safety, transactions, and rollback

| Requirement | DESIGN.md section | Status | Test reference |
|---|---|---|---|
| Clean-operation policy: no conflict-accepting merge/rebase/cherry-pick flows | Merge strategy | covered | `tests/test_update_cli_integration.py::test_cli_update_reports_rebase_conflict_recovery_guidance`; `tests/test_absorb_integration.py::test_absorb_reports_explicit_target_rebase_conflict_recovery_guidance` |
| Atomic multi-branch/worktree operations | Merge strategy | covered | `tests/test_safety_critical_integration.py::test_transaction_rolls_back_mutations_on_failure` |
| Backup refs under `refs/gitcuttle/txn/<txn-id>/...` for touched branches | Merge strategy (minimum rollback mechanism) | covered | `tests/test_safety_critical_integration.py::test_transaction_rolls_back_mutations_on_failure` |
| Rollback failure reports exact partial state and deterministic recovery commands | Merge strategy | covered | `tests/test_safety_critical_integration.py::test_transaction_rollback_failure_reports_partial_state` |

## Metadata and tracking contracts

| Requirement | DESIGN.md section | Status | Test reference / plan |
|---|---|---|---|
| `workspaces.json` schema v1 validation and invariants | Persistent Data -> workspaces.json schema | covered | `tests/test_metadata_cli_lifecycle_integration.py::test_cli_mutating_command_rejects_workspace_branch_key_mismatch` |
| Canonical repo identity keyed by git dir realpath | Persistent Data -> workspaces.json schema (invariants) | covered | `tests/test_metadata_cli_lifecycle_integration.py::test_cli_mutating_commands_from_worktree_use_single_repo_identity`; `tests/test_metadata_cli_lifecycle_integration.py::test_cli_mutating_command_rejects_noncanonical_repo_identity_key` |
| Atomic metadata writes | Merge strategy (minimum rollback mechanism) | covered | `tests/test_metadata_cli_lifecycle_integration.py::test_cli_new_preserves_metadata_file_on_atomic_replace_failure` |
| Schema migration creates backup before write | Persistent Data | covered | `tests/test_metadata_cli_lifecycle_integration.py::test_cli_mutating_command_migrates_existing_metadata` |
| Workspace path derivation and deterministic collision handling | Persistent Data -> Workspace path derivation | covered | `tests/test_new_cli_integration.py::test_cli_new_collision_uses_deterministic_paths_and_unsanitized_metadata_keys` |
| Mutating commands auto-track repo; read-only commands do not create tracking entries | Command Scope and Tracking | covered | `tests/test_metadata_cli_lifecycle_integration.py::test_cli_list_does_not_create_tracking_metadata`; `tests/test_metadata_cli_lifecycle_integration.py::test_cli_mutating_commands_from_worktree_use_single_repo_identity` |

## Remote and cache contracts

| Requirement | DESIGN.md section | Status | Planned coverage |
|---|---|---|---|
| `list` uses short TTL status cache (default 60s) | Persistent Data -> Status cache | covered | `tests/test_list_cli_integration.py::test_list_reuses_status_cache_within_ttl`; `tests/test_list_cli_integration.py::test_list_refreshes_status_cache_after_ttl_expiry` |
| Cache refresh does not create tracking entries | Persistent Data -> Status cache | covered | `tests/test_metadata_cli_lifecycle_integration.py::test_cli_list_cache_refresh_never_creates_tracking_metadata` |
| Prune treats unknown PR status as not merged | Use Cases -> Prune | covered | `tests/test_delete_prune_integration.py::test_prune_does_not_remove_branch_for_unknown_pr_state` |
