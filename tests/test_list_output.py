from pathlib import Path

from git_cuttle.list_output import TABLE_HEADERS, UNKNOWN_MARKER, render_workspace_table, rows_for_repo
from git_cuttle.metadata_manager import RepoMetadata, WorkspaceMetadata
from git_cuttle.remote_status import PullRequestStatus, RemoteAheadBehindStatus


def _workspace(*, branch: str, kind: str = "standard", base_ref: str = "main") -> WorkspaceMetadata:
    return WorkspaceMetadata(
        branch=branch,
        worktree_path=Path(f"/tmp/{branch.replace('/', '-')}-wt"),
        tracked_remote="origin",
        kind=kind,
        base_ref=base_ref,
        octopus_parents=("main", "release") if kind == "octopus" else (),
        created_at="2026-03-02T00:00:00Z",
        updated_at="2026-03-02T00:00:00Z",
    )


def _repo() -> RepoMetadata:
    workspaces = {
        "feature/alpha": _workspace(branch="feature/alpha"),
        "integration/merge": _workspace(
            branch="integration/merge",
            kind="octopus",
            base_ref="main",
        ),
    }
    return RepoMetadata(
        git_dir=Path("/tmp/repo/.git"),
        repo_root=Path("/tmp/repo"),
        default_remote="origin",
        tracked_at="2026-03-02T00:00:00Z",
        updated_at="2026-03-02T00:00:00Z",
        workspaces=workspaces,
    )


def test_rows_for_repo_populates_table_columns() -> None:
    repo = _repo()
    rows = rows_for_repo(
        repo=repo,
        remote_statuses={
            "feature/alpha": RemoteAheadBehindStatus(
                branch="feature/alpha",
                upstream_ref="origin/feature/alpha",
                ahead=2,
                behind=1,
            ),
            "integration/merge": RemoteAheadBehindStatus(
                branch="integration/merge",
                upstream_ref="origin/integration/merge",
                ahead=0,
                behind=0,
            ),
        },
        pr_statuses={
            "feature/alpha": PullRequestStatus(
                branch="feature/alpha",
                upstream_ref="origin/feature/alpha",
                state="open",
                title="Alpha",
                url="https://example.test/pr/1",
            ),
            "integration/merge": PullRequestStatus(
                branch="integration/merge",
                upstream_ref="origin/integration/merge",
                state="merged",
                title="Merge",
                url="https://example.test/pr/2",
            ),
        },
    )

    rendered = render_workspace_table(rows)
    assert all(header in rendered for header in TABLE_HEADERS)
    assert "feature/alpha" in rendered
    assert "octopus" in rendered
    assert "origin/feature/alpha" in rendered
    assert "open" in rendered


def test_rows_for_repo_uses_unknown_markers_for_missing_or_unknown_status() -> None:
    repo = _repo()
    rows = rows_for_repo(
        repo=repo,
        remote_statuses={
            "feature/alpha": RemoteAheadBehindStatus(
                branch="feature/alpha",
                upstream_ref=None,
                ahead=None,
                behind=None,
            )
        },
        pr_statuses={
            "feature/alpha": PullRequestStatus(
                branch="feature/alpha",
                upstream_ref=None,
                state="unknown",
                title=None,
                url=None,
            )
        },
    )

    rendered = render_workspace_table(rows)
    assert f" {UNKNOWN_MARKER} " in rendered
    assert "unknown" in rendered


def test_render_workspace_table_handles_empty_rows() -> None:
    rendered = render_workspace_table([])
    assert "(no tracked workspaces)" in rendered
