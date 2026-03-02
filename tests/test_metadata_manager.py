import json
import subprocess
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


def _init_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-b", "main"], check=True, cwd=path)
    subprocess.run(["git", "config", "user.name", "Test User"], check=True, cwd=path)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        check=True,
        cwd=path,
    )
    (path / "README.md").write_text("repo\n")
    subprocess.run(["git", "add", "README.md"], check=True, cwd=path)
    subprocess.run(["git", "commit", "-m", "init"], check=True, cwd=path)


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


def test_write_validates_repo_key_matches_canonical_git_dir(tmp_path: Path) -> None:
    manager = MetadataManager(path=tmp_path / "workspaces.json")

    with pytest.raises(
        ValueError, match="repo key must match canonical repo.git_dir realpath"
    ):
        manager.write(_metadata(repo_key="/repos/demo"))


def test_write_validates_repo_git_dir_is_canonical_realpath(tmp_path: Path) -> None:
    manager = MetadataManager(path=tmp_path / "workspaces.json")
    real_repo = tmp_path / "real-repo"
    real_repo.mkdir()
    (real_repo / ".git").mkdir()
    symlink_repo = tmp_path / "symlink-repo"
    symlink_repo.symlink_to(real_repo, target_is_directory=True)

    canonical_git_dir = (real_repo / ".git").resolve(strict=False)
    metadata = WorkspacesMetadata(
        version=SCHEMA_VERSION,
        repos={
            str(canonical_git_dir): RepoMetadata(
                git_dir=symlink_repo / ".git",
                repo_root=real_repo,
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

    with pytest.raises(
        ValueError, match="repo.git_dir must be stored as canonical realpath"
    ):
        manager.write(metadata)


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


def test_read_migrates_legacy_schema_and_creates_backup(tmp_path: Path) -> None:
    metadata_path = tmp_path / "workspaces.json"
    legacy_payload: dict[str, object] = {
        "version": 0,
        "repos": {
            "/repos/demo/.git": {
                "git_dir": "/repos/demo/.git",
                "repo_root": "/repos/demo",
                "default_remote": None,
                "tracked_at": "2026-03-01T00:00:00+00:00",
                "updated_at": "2026-03-01T00:00:00+00:00",
                "workspaces": {
                    "feature/a": {
                        "branch": "feature/a",
                        "worktree_path": "/wt/feature-a",
                        "tracked_remote": None,
                        "kind": "standard",
                        "base_ref": "main",
                        "octopus_parents": list[str](),
                        "created_at": "2026-03-01T00:00:00+00:00",
                        "updated_at": "2026-03-01T00:00:00+00:00",
                    }
                },
            }
        },
    }
    original_text = json.dumps(legacy_payload, indent=2)
    metadata_path.write_text(original_text)

    manager = MetadataManager(path=metadata_path)
    metadata = manager.read()

    assert metadata.version == SCHEMA_VERSION
    migrated_raw = json.loads(metadata_path.read_text())
    assert migrated_raw["version"] == SCHEMA_VERSION

    backups = sorted(tmp_path.glob("workspaces.json.bak.*"))
    assert len(backups) == 1
    assert backups[0].read_text() == original_text


def test_read_rejects_newer_schema_version(tmp_path: Path) -> None:
    metadata_path = tmp_path / "workspaces.json"
    metadata_path.write_text(json.dumps({"version": SCHEMA_VERSION + 1, "repos": {}}, indent=2))

    manager = MetadataManager(path=metadata_path)

    with pytest.raises(ValueError, match="unsupported metadata schema version"):
        manager.read()


def test_ensure_repo_tracked_creates_repo_entry(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    subprocess.run(
        ["git", "remote", "add", "origin", "git@example.com:acme/repo.git"],
        check=True,
        cwd=repo,
    )

    metadata_path = tmp_path / "workspaces.json"
    manager = MetadataManager(path=metadata_path)

    manager.ensure_repo_tracked(cwd=repo, now=lambda: "2026-03-01T00:00:00Z")

    metadata = manager.read()
    assert len(metadata.repos) == 1
    tracked_repo = next(iter(metadata.repos.values()))
    assert tracked_repo.repo_root == repo.resolve(strict=False)
    assert tracked_repo.default_remote == "origin"
    assert tracked_repo.tracked_at == "2026-03-01T00:00:00Z"
    assert tracked_repo.updated_at == "2026-03-01T00:00:00Z"
    assert tracked_repo.workspaces == {}


def test_ensure_repo_tracked_updates_existing_repo(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    metadata_path = tmp_path / "workspaces.json"
    manager = MetadataManager(path=metadata_path)

    manager.ensure_repo_tracked(cwd=repo, now=lambda: "2026-03-01T00:00:00Z")
    subprocess.run(
        ["git", "remote", "add", "upstream", "git@example.com:acme/upstream.git"],
        check=True,
        cwd=repo,
    )
    manager.ensure_repo_tracked(cwd=repo, now=lambda: "2026-03-02T00:00:00Z")

    metadata = manager.read()
    tracked_repo = next(iter(metadata.repos.values()))
    assert tracked_repo.default_remote == "upstream"
    assert tracked_repo.tracked_at == "2026-03-01T00:00:00Z"
    assert tracked_repo.updated_at == "2026-03-02T00:00:00Z"
