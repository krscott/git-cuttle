from dataclasses import dataclass
from pathlib import Path
import subprocess

from git_cuttle.metadata_manager import RepoMetadata
from git_cuttle.remote_status import PullRequestStatus, RemoteAheadBehindStatus


UNKNOWN_MARKER = "?"
TABLE_HEADERS = ("REPO", "BRANCH", "DIRTY", "AHEAD", "BEHIND", "PR", "DESCRIPTION", "WORKTREE")


@dataclass(kw_only=True, frozen=True)
class ListWorkspaceRow:
    repo: str
    branch: str
    dirty: str
    ahead: str
    behind: str
    pull_request: str
    description: str
    worktree_path: str


def rows_for_repo(
    *,
    repo: RepoMetadata,
    remote_statuses: dict[str, RemoteAheadBehindStatus],
    pr_statuses: dict[str, PullRequestStatus],
) -> list[ListWorkspaceRow]:
    rows: list[ListWorkspaceRow] = []
    for branch in sorted(repo.workspaces):
        workspace = repo.workspaces[branch]
        remote = remote_statuses.get(branch)
        pr = pr_statuses.get(branch)

        rows.append(
            ListWorkspaceRow(
                repo=repo.repo_root.name,
                branch=workspace.branch,
                dirty=_dirty_marker(workspace_path=workspace.worktree_path),
                ahead=_remote_count(remote, "ahead"),
                behind=_remote_count(remote, "behind"),
                pull_request=_pr_marker(pr),
                description=_description_for_workspace(
                    repo_root=repo.repo_root,
                    branch=workspace.branch,
                    pr=pr,
                ),
                worktree_path=str(workspace.worktree_path),
            )
        )
    return rows


def render_workspace_table(rows: list[ListWorkspaceRow]) -> str:
    table_rows = [
        [
            row.repo,
            row.branch,
            row.dirty,
            row.ahead,
            row.behind,
            row.pull_request,
            row.description,
            row.worktree_path,
        ]
        for row in rows
    ]

    widths = [len(header) for header in TABLE_HEADERS]
    for table_row in table_rows:
        for index, value in enumerate(table_row):
            widths[index] = max(widths[index], len(value))

    lines = [_format_row(values=TABLE_HEADERS, widths=widths)]
    for table_row in table_rows:
        lines.append(_format_row(values=tuple(table_row), widths=widths))

    if not table_rows:
        lines.append("(no tracked workspaces)")

    return "\n".join(lines)


def _remote_count(remote: RemoteAheadBehindStatus | None, field: str) -> str:
    if remote is None:
        return UNKNOWN_MARKER
    if field == "ahead":
        value = remote.ahead
    else:
        value = remote.behind

    if value is None:
        return UNKNOWN_MARKER
    return str(value)


def _format_row(*, values: tuple[str, ...], widths: list[int]) -> str:
    return "  ".join(value.ljust(widths[index]) for index, value in enumerate(values))


def _pr_marker(pr: PullRequestStatus | None) -> str:
    if pr is None:
        return UNKNOWN_MARKER
    if pr.state in {"unknown", "unavailable"}:
        return UNKNOWN_MARKER
    return pr.state


def _description_for_workspace(*, repo_root: Path, branch: str, pr: PullRequestStatus | None) -> str:
    if pr is not None and pr.title is not None and pr.state in {"open", "closed", "merged", "draft"}:
        return pr.title

    try:
        result = subprocess.run(
            ["git", "show", "-s", "--format=%s", branch],
            capture_output=True,
            text=True,
            check=False,
            cwd=repo_root,
        )
    except OSError:
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def _dirty_marker(*, workspace_path: Path) -> str:
    if not workspace_path.exists():
        return UNKNOWN_MARKER

    result = subprocess.run(
        ["git", "status", "--porcelain"],
        capture_output=True,
        text=True,
        check=False,
        cwd=workspace_path,
    )
    if result.returncode != 0:
        return UNKNOWN_MARKER
    return "yes" if result.stdout.strip() else "no"
