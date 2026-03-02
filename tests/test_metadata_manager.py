from pathlib import Path

import pytest

from git_cuttle.metadata_manager import (
    SCHEMA_VERSION,
    MetadataManager,
    RepoMetadata,
    WorkspaceKind,
    WorkspaceMetadata,
    WorkspacesMetadata,
    default_metadata_path,
)


def _workspace(
    *, branch: str, path: str, kind: WorkspaceKind = "standard"
) -> WorkspaceMetadata:
    octopus_parents = () if kind == "standard" else ("main", "release")
    return WorkspaceMetadata(
        branch=branch,
        worktree_path=Path(path),
        tracked_remote=None,
        kind=kind,
        base_ref="main",
        octopus_parents=octopus_parents,
        created_at="2026-03-01T00:00:00+00:00",
        updated_at="2026-03-01T00:00:00+00:00",
    )


def _metadata(*, repo_key: str | None = None) -> WorkspacesMetadata:
    canonical_key = repo_key or "/repos/demo/.git"
    return WorkspacesMetadata(
        version=SCHEMA_VERSION,
        repos={
            canonical_key: RepoMetadata(
                git_dir=Path("/repos/demo/.git"),
                repo_root=Path("/repos/demo"),
                default_remote=None,
                tracked_at="2026-03-01T00:00:00+00:00",
                updated_at="2026-03-01T00:00:00+00:00",
                workspaces={
                    "feature/a": _workspace(
                        branch="feature/a", path="/wt/feature-a", kind="standard"
                    )
                },
            )
        },
    )


def test_default_metadata_path_honors_xdg_data_home(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", "/tmp/xdg")

    assert default_metadata_path() == Path("/tmp/xdg/gitcuttle/workspaces.json")


def test_read_returns_empty_schema_when_file_is_missing(tmp_path: Path) -> None:
    manager = MetadataManager(path=tmp_path / "workspaces.json")

    metadata = manager.read()

    assert metadata == WorkspacesMetadata(version=SCHEMA_VERSION, repos={})


def test_write_and_read_round_trip(tmp_path: Path) -> None:
    manager = MetadataManager(path=tmp_path / "meta" / "workspaces.json")
    expected = _metadata()

    manager.write(expected)
    actual = manager.read()

    assert actual == expected


def test_write_failure_does_not_clobber_existing_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager = MetadataManager(path=tmp_path / "meta" / "workspaces.json")
    original = _metadata()
    manager.write(original)

    updated = WorkspacesMetadata(
        version=SCHEMA_VERSION,
        repos={
            "/repos/demo/.git": RepoMetadata(
                git_dir=Path("/repos/demo/.git"),
                repo_root=Path("/repos/demo"),
                default_remote="origin",
                tracked_at="2026-03-01T00:00:00+00:00",
                updated_at="2026-03-02T00:00:00+00:00",
                workspaces={
                    "feature/a": _workspace(
                        branch="feature/a", path="/wt/feature-a", kind="standard"
                    )
                },
            )
        },
    )

    def broken_replace(_src: str | Path, _dst: str | Path) -> None:
        raise OSError("simulated replace failure")

    monkeypatch.setattr("git_cuttle.metadata_manager.os.replace", broken_replace)

    with pytest.raises(OSError, match="simulated replace failure"):
        manager.write(updated)

    assert manager.read() == original
    temp_files = list((tmp_path / "meta").glob("*.tmp"))
    assert temp_files == []


def test_write_validates_repo_key_matches_git_dir(tmp_path: Path) -> None:
    manager = MetadataManager(path=tmp_path / "workspaces.json")

    with pytest.raises(ValueError, match="repo key must match repo.git_dir exactly"):
        manager.write(_metadata(repo_key="/repos/demo"))


def test_write_validates_workspace_key_matches_branch(tmp_path: Path) -> None:
    manager = MetadataManager(path=tmp_path / "workspaces.json")
    metadata = _metadata()
    repo = metadata.repos["/repos/demo/.git"]
    invalid = WorkspacesMetadata(
        version=SCHEMA_VERSION,
        repos={
            "/repos/demo/.git": RepoMetadata(
                git_dir=repo.git_dir,
                repo_root=repo.repo_root,
                default_remote=repo.default_remote,
                tracked_at=repo.tracked_at,
                updated_at=repo.updated_at,
                workspaces={
                    "feature/wrong": _workspace(
                        branch="feature/right", path="/wt/feature-right", kind="standard"
                    )
                },
            )
        },
    )

    with pytest.raises(
        ValueError, match="workspace key must match workspace.branch exactly"
    ):
        manager.write(invalid)


def test_write_validates_workspace_kind_invariants(tmp_path: Path) -> None:
    manager = MetadataManager(path=tmp_path / "workspaces.json")
    repo = _metadata().repos["/repos/demo/.git"]
    invalid = WorkspacesMetadata(
        version=SCHEMA_VERSION,
        repos={
            "/repos/demo/.git": RepoMetadata(
                git_dir=repo.git_dir,
                repo_root=repo.repo_root,
                default_remote=repo.default_remote,
                tracked_at=repo.tracked_at,
                updated_at=repo.updated_at,
                workspaces={
                    "feature/a": WorkspaceMetadata(
                        branch="feature/a",
                        worktree_path=Path("/wt/feature-a"),
                        tracked_remote=None,
                        kind="octopus",
                        base_ref="main",
                        octopus_parents=("main",),
                        created_at="2026-03-01T00:00:00+00:00",
                        updated_at="2026-03-01T00:00:00+00:00",
                    )
                },
            )
        },
    )

    with pytest.raises(ValueError, match="octopus workspaces must have at least two parents"):
        manager.write(invalid)
