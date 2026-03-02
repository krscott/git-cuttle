from dataclasses import dataclass, replace
from pathlib import Path
import subprocess
from typing import Literal

from git_cuttle.errors import AppError
from git_cuttle.git_ops import canonical_git_dir, repo_root
from git_cuttle.metadata_manager import MetadataManager, WorkspaceMetadata, WorkspacesMetadata
from git_cuttle.plan_output import DryRunPlan, PlanAction, render_human_plan, render_json_plan

PrStatus = Literal["merged", "open", "closed", "unknown", "unavailable"]
PruneReason = Literal["missing-local-branch", "merged-pr"]
PruneBlockReason = Literal["current-workspace", "workspace-dirty"]


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
        repo_workspaces=repo.workspaces,
    )
    plan = _build_prune_plan(decisions=decisions, force=force)
    if dry_run:
        return render_json_plan(plan) if json_output else render_human_plan(plan)

    pruned_branches = {decision.branch for decision in decisions if decision.block_reason is None}
    for decision in decisions:
        if decision.block_reason is not None:
            continue

        if decision.worktree_path.exists():
            _remove_worktree(
                repo_root=repo_root_dir,
                worktree_path=decision.worktree_path,
                force=force,
            )

        if decision.local_branch_exists:
            _delete_local_branch(
                repo_root=repo_root_dir,
                branch=decision.branch,
                force=force,
            )

    if not pruned_branches:
        return None

    updated_workspaces = {
        name: workspace for name, workspace in repo.workspaces.items() if name not in pruned_branches
    }
    updated_repo = replace(repo, workspaces=updated_workspaces)
    updated_repos = dict(metadata.repos)
    updated_repos[repo_key] = updated_repo
    metadata_manager.write(WorkspacesMetadata(version=metadata.version, repos=updated_repos))
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
) -> PruneBlockReason | None:
    if force:
        return None
    if current == target:
        return "current-workspace"
    if worktree_path.exists() and _worktree_has_uncommitted_changes(cwd=worktree_path):
        return "workspace-dirty"
    return None


def _build_prune_plan(*, decisions: tuple[PruneDecision, ...], force: bool) -> DryRunPlan:
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
        actions.append(PlanAction(op="untrack-workspace", target=decision.branch, details=decision.reason))

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
