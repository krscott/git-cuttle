from dataclasses import dataclass

from git_cuttle.metadata_manager import RepoMetadata
from git_cuttle.remote_status import PullRequestStatus, RemoteAheadBehindStatus


UNKNOWN_MARKER = "?"
TABLE_HEADERS = (
    "BRANCH",
    "KIND",
    "BASE",
    "UPSTREAM",
    "AHEAD",
    "BEHIND",
    "PR",
    "WORKTREE",
)


@dataclass(kw_only=True, frozen=True)
class ListWorkspaceRow:
    branch: str
    kind: str
    base_ref: str
    upstream_ref: str
    ahead: str
    behind: str
    pull_request: str
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
                branch=workspace.branch,
                kind=workspace.kind,
                base_ref=workspace.base_ref,
                upstream_ref=_remote_upstream(remote),
                ahead=_remote_count(remote, "ahead"),
                behind=_remote_count(remote, "behind"),
                pull_request=pr.state if pr is not None else UNKNOWN_MARKER,
                worktree_path=str(workspace.worktree_path),
            )
        )
    return rows


def render_workspace_table(rows: list[ListWorkspaceRow]) -> str:
    table_rows = [
        [
            row.branch,
            row.kind,
            row.base_ref,
            row.upstream_ref,
            row.ahead,
            row.behind,
            row.pull_request,
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


def _remote_upstream(remote: RemoteAheadBehindStatus | None) -> str:
    if remote is None or remote.upstream_ref is None:
        return UNKNOWN_MARKER
    return remote.upstream_ref


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
