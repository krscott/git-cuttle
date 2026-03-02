from dataclasses import dataclass
from typing import Literal

PrStatus = Literal["merged", "open", "closed", "unknown", "unavailable"]
PruneReason = Literal["missing-local-branch", "merged-pr"]


@dataclass(kw_only=True, frozen=True)
class PruneCandidate:
    branch: str
    local_branch_exists: bool
    pr_status: PrStatus | None


def prune_reason(candidate: PruneCandidate) -> PruneReason | None:
    if not candidate.local_branch_exists:
        return "missing-local-branch"
    if candidate.pr_status == "merged":
        return "merged-pr"
    return None
