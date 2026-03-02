from git_cuttle.prune import PruneCandidate, prune_reason


def test_prune_reason_is_missing_local_branch_when_branch_no_longer_exists() -> None:
    candidate = PruneCandidate(
        branch="feature/missing",
        local_branch_exists=False,
        pr_status="unknown",
    )

    assert prune_reason(candidate) == "missing-local-branch"


def test_prune_reason_is_merged_pr_when_pr_is_merged() -> None:
    candidate = PruneCandidate(
        branch="feature/merged",
        local_branch_exists=True,
        pr_status="merged",
    )

    assert prune_reason(candidate) == "merged-pr"


def test_prune_reason_does_not_prune_unknown_or_unavailable_pr_states() -> None:
    unknown_candidate = PruneCandidate(
        branch="feature/unknown",
        local_branch_exists=True,
        pr_status="unknown",
    )
    unavailable_candidate = PruneCandidate(
        branch="feature/unavailable",
        local_branch_exists=True,
        pr_status="unavailable",
    )
    no_pr_candidate = PruneCandidate(
        branch="feature/no-pr",
        local_branch_exists=True,
        pr_status=None,
    )

    assert prune_reason(unknown_candidate) is None
    assert prune_reason(unavailable_candidate) is None
    assert prune_reason(no_pr_candidate) is None
