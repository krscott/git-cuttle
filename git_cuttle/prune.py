from dataclasses import dataclass
from pathlib import Path
import subprocess
from typing import Literal

PrStatus = Literal["merged", "open", "closed", "unknown", "unavailable"]
PruneReason = Literal["missing-local-branch", "merged-pr"]


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
