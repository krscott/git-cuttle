import subprocess
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal

from git_cuttle.errors import AppError
from git_cuttle.git_ops import add_worktree
from git_cuttle.git_ops import canonical_git_dir, repo_root
from git_cuttle.metadata_manager import (
    MetadataManager,
    WorkspaceMetadata,
    WorkspacesMetadata,
)
from git_cuttle.plan_output import (
    DryRunPlan,
    PlanAction,
    render_human_plan,
    render_json_plan,
)
from git_cuttle.transaction import Transaction, TransactionStep
from git_cuttle.workspace_transaction import (
    backup_refs_step,
    cleanup_backup_refs_post_commit,
    rollback_restore_branch,
    run_command_transaction,
)

PrStatus = Literal["merged", "open", "closed", "unknown", "unavailable"]
PruneReason = Literal["missing-local-branch", "merged-pr"]
PruneBlockReason = Literal[
    "current-workspace",
    "workspace-dirty",
    "no-upstream",
    "ahead-of-upstream",
]


@dataclass(kw_only=True, frozen=True)
class PruneDecision:
    branch: str
    reason: PruneReason
    block_reason: PruneBlockReason | None
    local_branch_exists: bool
    worktree_path: Path


@dataclass(kw_only=True, frozen=True)
class PruneCandidate:
    branch: str
    local_branch_exists: bool
    pr_status: PrStatus | None


def local_branch_exists(*, repo_root: Path, branch: str) -> bool:
    result = subprocess.run(
        ["git", "show-ref", "--verify", "--quiet", f"refs/heads/{branch}"],
        capture_output=True,
        text=True,
        check=False,
        cwd=repo_root,
    )
    return result.returncode == 0


def prune_candidate_for_branch(
    *,
    repo_root: Path,
    branch: str,
    pr_status: PrStatus | None,
) -> PruneCandidate:
    return PruneCandidate(
        branch=branch,
        local_branch_exists=local_branch_exists(repo_root=repo_root, branch=branch),
        pr_status=pr_status,
    )


def prune_reason(candidate: PruneCandidate) -> PruneReason | None:
    if not candidate.local_branch_exists:
        return "missing-local-branch"
    if candidate.pr_status == "merged":
        return "merged-pr"
    return None


def prune_workspaces(
    *,
    cwd: Path,
    metadata_manager: MetadataManager,
    pr_status_by_branch: dict[str, PrStatus | None] | None = None,
    force: bool = False,
    dry_run: bool = False,
    json_output: bool = False,
) -> str | None:
    repo_git_dir = canonical_git_dir(cwd)
    if repo_git_dir is None or repo_root(cwd) is None:
        raise AppError(
            code="not-in-git-repo",
            message="gitcuttle must be run from within a git repository",
        )

    metadata = metadata_manager.read()
    repo = metadata.repos.get(str(repo_git_dir))
    if repo is None:
        common_git_dir = _git_common_dir(cwd=cwd)
        if common_git_dir is not None:
            repo = metadata.repos.get(str(common_git_dir))
    if repo is None:
        raise AppError(
            code="repo-not-tracked",
            message="repository metadata is missing",
            guidance=("rerun the command to retry auto-tracking",),
        )

    repo_root_dir = repo.repo_root
    repo_key = str(repo.git_dir)

    statuses = pr_status_by_branch or {}
    current = current_branch(cwd=cwd)
    decisions = _prune_decisions(
        repo_root=repo_root_dir,
        statuses=statuses,
        force=force,
        current=current,
        default_remote=repo.default_remote,
        repo_workspaces=repo.workspaces,
    )
    plan = _build_prune_plan(decisions=decisions, force=force)
    if dry_run:
        return render_json_plan(plan) if json_output else render_human_plan(plan)

    executable_decisions = tuple(
        decision for decision in decisions if decision.block_reason is None
    )
    pruned_branches = {decision.branch for decision in executable_decisions}
    if not pruned_branches:
        return None

    updated_workspaces = {
        name: workspace
        for name, workspace in repo.workspaces.items()
        if name not in pruned_branches
    }
    updated_repo = replace(repo, workspaces=updated_workspaces)
    updated_repos = dict(metadata.repos)
    updated_repos[repo_key] = updated_repo

    updated_metadata = WorkspacesMetadata(version=metadata.version, repos=updated_repos)
    transaction = Transaction()
    backup_branches = tuple(
        decision.branch
        for decision in executable_decisions
        if decision.local_branch_exists
    )
    if backup_branches:
        transaction.add_step(
            backup_refs_step(
                repo_root=repo_root_dir,
                transaction=transaction,
                branches=backup_branches,
                backup_error_code="prune-backup-failed",
                backup_error_message="failed to create transactional backup refs for prune",
                rollback_error_code="prune-rollback-failed",
                rollback_error_message="failed to rollback backup refs during prune",
            )
        )

    for decision in executable_decisions:
        if decision.worktree_path.exists():
            detached_oid: str | None = None
            if not decision.local_branch_exists:
                detached_oid = _worktree_head_oid(worktree_path=decision.worktree_path)
            transaction.add_step(
                _remove_worktree_step(
                    repo_root=repo_root_dir,
                    decision=decision,
                    force=force,
                    detached_oid=detached_oid,
                )
            )

        if decision.local_branch_exists:
            transaction.add_step(
                _delete_branch_step(
                    repo_root=repo_root_dir,
                    transaction=transaction,
                    decision=decision,
                    force=force,
                )
            )

    transaction.add_step(
        TransactionStep(
            name="write-metadata",
            apply=lambda: metadata_manager.write(updated_metadata),
            rollback=lambda: metadata_manager.write(metadata),
        )
    )
    run_command_transaction(
        transaction=transaction,
        code="prune-failed",
        message="failed to prune workspaces",
    )
    cleanup_backup_refs_post_commit(
        repo_root=repo_root_dir,
        transaction=transaction,
        branches=backup_branches,
        cleanup_error_code="prune-cleanup-failed",
        cleanup_error_message="failed to cleanup transactional backup refs for prune",
    )
    return None


def _git_common_dir(*, cwd: Path) -> Path | None:
    result = subprocess.run(
        ["git", "rev-parse", "--git-common-dir"],
        capture_output=True,
        text=True,
        check=False,
        cwd=cwd,
    )
    if result.returncode != 0:
        return None

    common = Path(result.stdout.strip())
    if common.is_absolute():
        return common.resolve(strict=False)
    return (cwd / common).resolve(strict=False)


def _prune_decisions(
    *,
    repo_root: Path,
    statuses: dict[str, PrStatus | None],
    force: bool,
    current: str | None,
    default_remote: str | None,
    repo_workspaces: dict[str, WorkspaceMetadata],
) -> tuple[PruneDecision, ...]:
    decisions: list[PruneDecision] = []
    for branch, workspace in sorted(repo_workspaces.items()):
        candidate = prune_candidate_for_branch(
            repo_root=repo_root,
            branch=branch,
            pr_status=statuses.get(branch),
        )
        reason = prune_reason(candidate)
        if reason is None:
            continue

        worktree_path = workspace.worktree_path
        block_reason = prune_block_reason(
            current=current,
            target=branch,
            worktree_path=worktree_path,
            force=force,
            reason=reason,
            repo_root=repo_root,
            tracked_remote=workspace.tracked_remote,
            default_remote=default_remote,
        )
        decisions.append(
            PruneDecision(
                branch=branch,
                reason=reason,
                block_reason=block_reason,
                local_branch_exists=candidate.local_branch_exists,
                worktree_path=worktree_path,
            )
        )

    return tuple(decisions)


def prune_block_reason(
    *,
    current: str | None,
    target: str,
    worktree_path: Path,
    force: bool,
    reason: PruneReason,
    repo_root: Path,
    tracked_remote: str | None,
    default_remote: str | None,
) -> PruneBlockReason | None:
    if force:
        return None
    if current == target:
        return "current-workspace"
    if worktree_path.exists() and _worktree_has_uncommitted_changes(cwd=worktree_path):
        return "workspace-dirty"
    if reason == "missing-local-branch":
        return None

    upstream_ref = _workspace_upstream_ref(
        tracked_remote=tracked_remote,
        default_remote=default_remote,
        branch=target,
    )
    if upstream_ref is None:
        return "no-upstream"

    if not _ref_exists(repo_root=repo_root, ref=f"refs/remotes/{upstream_ref}"):
        return "no-upstream"

    ahead = _ahead_count(
        repo_root=repo_root, local_branch=target, upstream_ref=upstream_ref
    )
    if ahead is None:
        return "no-upstream"
    if ahead > 0:
        return "ahead-of-upstream"

    return None


def _workspace_upstream_ref(
    *, tracked_remote: str | None, default_remote: str | None, branch: str
) -> str | None:
    remote_name = tracked_remote or default_remote
    if remote_name is None:
        return None
    return f"{remote_name}/{branch}"


def _ref_exists(*, repo_root: Path, ref: str) -> bool:
    result = subprocess.run(
        ["git", "rev-parse", "--verify", ref],
        capture_output=True,
        text=True,
        check=False,
        cwd=repo_root,
    )
    return result.returncode == 0


def _ahead_count(
    *, repo_root: Path, local_branch: str, upstream_ref: str
) -> int | None:
    result = subprocess.run(
        [
            "git",
            "rev-list",
            "--left-right",
            "--count",
            f"{local_branch}...{upstream_ref}",
        ],
        capture_output=True,
        text=True,
        check=False,
        cwd=repo_root,
    )
    if result.returncode != 0:
        return None

    parts = result.stdout.strip().split()
    if len(parts) != 2:
        return None

    try:
        return int(parts[0])
    except ValueError:
        return None


def _build_prune_plan(
    *, decisions: tuple[PruneDecision, ...], force: bool
) -> DryRunPlan:
    actions: list[PlanAction] = []
    warnings: list[str] = []
    for decision in decisions:
        if decision.block_reason is not None:
            warnings.append(
                f"skipping {decision.branch}: blocked by {decision.block_reason}; rerun with --force"
            )
            continue

        actions.append(
            PlanAction(
                op="delete-worktree",
                target=str(decision.worktree_path),
                details=decision.reason,
            )
        )
        if decision.local_branch_exists:
            actions.append(
                PlanAction(
                    op="delete-branch",
                    target=decision.branch,
                    details="forced" if force else decision.reason,
                )
            )
        actions.append(
            PlanAction(
                op="untrack-workspace", target=decision.branch, details=decision.reason
            )
        )

    return DryRunPlan(command="prune", actions=tuple(actions), warnings=tuple(warnings))


def current_branch(*, cwd: Path) -> str | None:
    result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
        cwd=cwd,
    )
    if result.returncode != 0:
        return None

    branch = result.stdout.strip()
    if branch == "" or branch == "HEAD":
        return None
    return branch


def _worktree_has_uncommitted_changes(*, cwd: Path) -> bool:
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        capture_output=True,
        text=True,
        check=False,
        cwd=cwd,
    )
    return result.returncode == 0 and bool(result.stdout.strip())


def _remove_worktree(*, repo_root: Path, worktree_path: Path, force: bool) -> None:
    args = ["git", "worktree", "remove"]
    if force:
        args.append("--force")
    args.append(str(worktree_path))

    result = subprocess.run(
        args,
        capture_output=True,
        text=True,
        check=False,
        cwd=repo_root,
    )
    if result.returncode != 0:
        raise AppError(
            code="worktree-delete-failed",
            message="failed to delete workspace worktree",
            details=result.stderr.strip() or str(worktree_path),
        )


def _delete_local_branch(*, repo_root: Path, branch: str, force: bool) -> None:
    delete_flag = "-D" if force else "-d"
    result = subprocess.run(
        ["git", "branch", delete_flag, branch],
        capture_output=True,
        text=True,
        check=False,
        cwd=repo_root,
    )
    if result.returncode != 0:
        raise AppError(
            code="branch-delete-failed",
            message="failed to delete workspace branch",
            details=result.stderr.strip() or branch,
        )


def _worktree_head_oid(*, worktree_path: Path) -> str | None:
    result = subprocess.run(
        ["git", "rev-parse", "--verify", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
        cwd=worktree_path,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def _restore_pruned_worktree(
    *,
    repo_root: Path,
    branch: str,
    worktree_path: Path,
    local_branch_exists: bool,
    detached_oid: str | None,
) -> None:
    if worktree_path.exists():
        return

    if local_branch_exists:
        try:
            add_worktree(branch=branch, path=worktree_path, cwd=repo_root)
            return
        except RuntimeError as error:
            raise AppError(
                code="prune-rollback-failed",
                message="failed to restore workspace worktree during prune rollback",
                details=str(error),
            ) from error

    if detached_oid is None:
        return

    result = subprocess.run(
        ["git", "worktree", "add", "--detach", str(worktree_path), detached_oid],
        capture_output=True,
        text=True,
        check=False,
        cwd=repo_root,
    )
    if result.returncode != 0:
        raise AppError(
            code="prune-rollback-failed",
            message="failed to restore detached workspace worktree during prune rollback",
            details=result.stderr.strip() or detached_oid,
        )


def _remove_worktree_step(
    *,
    repo_root: Path,
    decision: PruneDecision,
    force: bool,
    detached_oid: str | None,
) -> TransactionStep:
    return TransactionStep(
        name=f"remove-worktree:{decision.branch}",
        apply=lambda: _remove_worktree(
            repo_root=repo_root,
            worktree_path=decision.worktree_path,
            force=force,
        ),
        rollback=lambda: _restore_pruned_worktree(
            repo_root=repo_root,
            branch=decision.branch,
            worktree_path=decision.worktree_path,
            local_branch_exists=decision.local_branch_exists,
            detached_oid=detached_oid,
        ),
    )


def _delete_branch_step(
    *,
    repo_root: Path,
    transaction: Transaction,
    decision: PruneDecision,
    force: bool,
) -> TransactionStep:
    return TransactionStep(
        name=f"delete-branch:{decision.branch}",
        apply=lambda: _delete_local_branch(
            repo_root=repo_root,
            branch=decision.branch,
            force=force,
        ),
        rollback=lambda: rollback_restore_branch(
            repo_root=repo_root,
            transaction=transaction,
            branch=decision.branch,
            error_code="prune-rollback-failed",
            message="failed to restore pruned branch from backup ref",
        ),
    )
