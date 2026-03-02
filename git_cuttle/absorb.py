from dataclasses import dataclass
from pathlib import Path
import subprocess
from typing import Callable

from git_cuttle.errors import AppError
from git_cuttle.metadata_manager import WorkspaceMetadata


CommitTargetChooser = Callable[[str, tuple[str, ...]], str]


@dataclass(kw_only=True, frozen=True)
class AbsorbedCommit:
    commit: str
    target_parent: str


@dataclass(kw_only=True, frozen=True)
class AbsorbResult:
    branch: str
    before_oid: str
    after_oid: str
    absorbed_commits: tuple[AbsorbedCommit, ...]

    @property
    def changed(self) -> bool:
        return self.before_oid != self.after_oid


def absorb_octopus_workspace(
    *,
    repo_root: Path,
    workspace: WorkspaceMetadata,
    target_parent: str | None = None,
    interactive: bool = False,
    choose_target: CommitTargetChooser | None = None,
) -> AbsorbResult:
    if workspace.kind != "octopus":
        raise AppError(
            code="invalid-workspace-kind",
            message="absorb requires octopus workspace metadata",
            details=workspace.branch,
        )
    if len(workspace.octopus_parents) < 2:
        raise AppError(
            code="invalid-octopus-parents",
            message="octopus workspace must track at least two parent refs",
            details=workspace.branch,
        )

    if target_parent is not None and target_parent not in workspace.octopus_parents:
        raise AppError(
            code="invalid-absorb-target",
            message="target parent is not part of the octopus workspace",
            details=target_parent,
            guidance=(
                "choose one of the configured octopus parent branches",
            ),
        )

    if interactive and choose_target is None:
        raise AppError(
            code="interactive-selection-unavailable",
            message="interactive absorb requires a commit target selector",
            guidance=(
                "pass a commit selection callback or run absorb with an explicit target parent",
            ),
        )

    before_oid = _branch_head(repo_root=repo_root, branch=workspace.branch)
    unique_commits = _octopus_unique_commits(
        repo_root=repo_root,
        branch=workspace.branch,
        parent_refs=workspace.octopus_parents,
    )
    merge_commit, post_merge_commits = _split_octopus_history(
        repo_root=repo_root,
        unique_commits=unique_commits,
    )

    if not post_merge_commits:
        return AbsorbResult(
            branch=workspace.branch,
            before_oid=before_oid,
            after_oid=before_oid,
            absorbed_commits=(),
        )

    planned = _plan_absorb_targets(
        repo_root=repo_root,
        commits=post_merge_commits,
        parents=workspace.octopus_parents,
        explicit_target=target_parent,
        interactive=interactive,
        chooser=choose_target,
    )

    original_branch = _current_branch(repo_root=repo_root)
    try:
        for item in planned:
            _checkout_branch(repo_root=repo_root, branch=item.target_parent)
            _git(
                repo_root=repo_root,
                args=["cherry-pick", item.commit],
                code="absorb-cherry-pick-failed",
                message="failed to cherry-pick commit onto target parent",
            )

        if merge_commit is not None:
            _checkout_branch(repo_root=repo_root, branch=workspace.branch)
            _git(
                repo_root=repo_root,
                args=["reset", "--hard", merge_commit],
                code="absorb-reset-failed",
                message="failed to reset octopus branch after absorb",
            )
    finally:
        if original_branch is not None and original_branch != _current_branch(repo_root=repo_root):
            _checkout_branch(repo_root=repo_root, branch=original_branch)

    after_oid = _branch_head(repo_root=repo_root, branch=workspace.branch)
    return AbsorbResult(
        branch=workspace.branch,
        before_oid=before_oid,
        after_oid=after_oid,
        absorbed_commits=tuple(planned),
    )


def _plan_absorb_targets(
    *,
    repo_root: Path,
    commits: list[str],
    parents: tuple[str, ...],
    explicit_target: str | None,
    interactive: bool,
    chooser: CommitTargetChooser | None,
) -> list[AbsorbedCommit]:
    planned: list[AbsorbedCommit] = []
    for commit in commits:
        if explicit_target is not None:
            target = explicit_target
        elif interactive:
            assert chooser is not None
            target = chooser(commit, parents)
        else:
            target = _heuristic_target_parent(repo_root=repo_root, commit=commit, parents=parents)

        if target not in parents:
            raise AppError(
                code="invalid-absorb-target",
                message="selected absorb target is not an octopus parent",
                details=f"{target} for commit {commit}",
            )

        planned.append(AbsorbedCommit(commit=commit, target_parent=target))

    return planned


def _heuristic_target_parent(*, repo_root: Path, commit: str, parents: tuple[str, ...]) -> str:
    changed_files = _commit_changed_files(repo_root=repo_root, commit=commit)
    if not changed_files:
        raise AppError(
            code="absorb-target-uncertain",
            message="cannot infer absorb target for empty or metadata-only commit",
            details=commit,
            guidance=(
                "rerun with an explicit parent branch or interactive mode (-i)",
            ),
        )

    scores: dict[str, int] = {}
    for parent in parents:
        matches = 0
        for changed_file in changed_files:
            if _path_exists_at_ref(repo_root=repo_root, ref=parent, path=changed_file):
                matches += 1
        scores[parent] = matches

    best_parent, best_score = max(scores.items(), key=lambda item: item[1])
    tied = sum(1 for score in scores.values() if score == best_score) > 1
    confidence = best_score / len(changed_files)
    if best_score == 0 or tied or confidence < 0.6:
        score_details = ", ".join(f"{parent}={score}" for parent, score in sorted(scores.items()))
        raise AppError(
            code="absorb-target-uncertain",
            message="could not infer a high-confidence absorb target",
            details=f"{commit}: {score_details}",
            guidance=(
                "rerun with an explicit parent branch or interactive mode (-i)",
            ),
        )

    return best_parent


def _split_octopus_history(*, repo_root: Path, unique_commits: list[str]) -> tuple[str | None, list[str]]:
    if not unique_commits:
        return None, []
    first_commit = unique_commits[0]
    if _is_merge_commit(repo_root=repo_root, commit=first_commit):
        return first_commit, unique_commits[1:]
    return None, unique_commits


def _commit_changed_files(*, repo_root: Path, commit: str) -> list[str]:
    result = subprocess.run(
        ["git", "show", "--pretty=", "--name-only", commit],
        capture_output=True,
        text=True,
        check=False,
        cwd=repo_root,
    )
    if result.returncode != 0:
        details = result.stderr.strip() or result.stdout.strip() or commit
        raise AppError(
            code="absorb-analysis-failed",
            message="failed to inspect changed files for absorb",
            details=details,
        )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _path_exists_at_ref(*, repo_root: Path, ref: str, path: str) -> bool:
    result = subprocess.run(
        ["git", "cat-file", "-e", f"{ref}:{path}"],
        capture_output=True,
        text=True,
        check=False,
        cwd=repo_root,
    )
    return result.returncode == 0


def _octopus_unique_commits(*, repo_root: Path, branch: str, parent_refs: tuple[str, ...]) -> list[str]:
    result = subprocess.run(
        ["git", "rev-list", "--reverse", branch, "--not", *parent_refs],
        capture_output=True,
        text=True,
        check=False,
        cwd=repo_root,
    )
    if result.returncode != 0:
        details = result.stderr.strip() or result.stdout.strip() or branch
        raise AppError(
            code="octopus-update-analysis-failed",
            message="failed to analyze octopus branch history",
            details=details,
        )

    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _is_merge_commit(*, repo_root: Path, commit: str) -> bool:
    parent_line = _git_stdout(repo_root=repo_root, args=["show", "-s", "--format=%P", commit])
    parent_oids = [parent for parent in parent_line.split() if parent]
    return len(parent_oids) > 1


def _branch_head(*, repo_root: Path, branch: str) -> str:
    branch_oid = _rev_parse(repo_root=repo_root, ref=f"refs/heads/{branch}")
    if branch_oid is None:
        raise AppError(
            code="branch-missing",
            message="workspace branch does not exist locally",
            details=branch,
            guidance=("fetch or recreate the local branch before running absorb",),
        )
    return branch_oid


def _rev_parse(*, repo_root: Path, ref: str) -> str | None:
    result = subprocess.run(
        ["git", "rev-parse", "--verify", ref],
        capture_output=True,
        text=True,
        check=False,
        cwd=repo_root,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def _current_branch(*, repo_root: Path) -> str | None:
    branch = _git_stdout(
        repo_root=repo_root,
        args=["rev-parse", "--abbrev-ref", "HEAD"],
        code="git-state-read-failed",
        message="failed to resolve current branch",
    )
    if branch == "" or branch == "HEAD":
        return None
    return branch


def _checkout_branch(*, repo_root: Path, branch: str) -> None:
    _git(
        repo_root=repo_root,
        args=["checkout", branch],
        code="branch-checkout-failed",
        message="failed to checkout branch",
    )


def _git(*, repo_root: Path, args: list[str], code: str, message: str) -> None:
    result = subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        check=False,
        cwd=repo_root,
    )
    if result.returncode != 0:
        details = result.stderr.strip() or result.stdout.strip() or " ".join(args)
        raise AppError(code=code, message=message, details=details)


def _git_stdout(
    *,
    repo_root: Path,
    args: list[str],
    code: str = "git-command-failed",
    message: str = "git command failed",
) -> str:
    result = subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        check=False,
        cwd=repo_root,
    )
    if result.returncode != 0:
        details = result.stderr.strip() or result.stdout.strip() or " ".join(args)
        raise AppError(code=code, message=message, details=details)
    return result.stdout.strip()
