import json
from pathlib import Path

import pytest

from git_cuttle.metadata_manager import MetadataManager, SCHEMA_VERSION


def _legacy_v0_payload(*, repo_key: str, repo_root: Path, worktree_path: Path) -> dict[str, object]:
    return {
        "version": 0,
        "repos": {
            repo_key: {
                "git_dir": repo_key,
                "repo_root": str(repo_root),
                "default_remote": None,
                "tracked_at": "2026-03-01T00:00:00+00:00",
                "updated_at": "2026-03-01T00:00:00+00:00",
                "workspaces": {
                    "feature/migrate": {
                        "branch": "feature/migrate",
                        "worktree_path": str(worktree_path),
                        "tracked_remote": None,
                        "kind": "standard",
                        "base_ref": "main",
                        "octopus_parents": [],
                        "created_at": "2026-03-01T00:00:00+00:00",
                        "updated_at": "2026-03-01T00:00:00+00:00",
                    }
                },
            }
        },
    }


@pytest.mark.integration
def test_read_rejects_invalid_schema_in_metadata_file(tmp_path: Path) -> None:
    metadata_path = tmp_path / "workspaces.json"
    metadata_path.write_text(
        json.dumps(
            {
                "version": SCHEMA_VERSION,
                "repos": {
                    "/tmp/repo/.git": {
                        "git_dir": "/tmp/repo/.git",
                        "repo_root": "/tmp/repo",
                        "default_remote": None,
                        "tracked_at": "2026-03-01T00:00:00+00:00",
                        "updated_at": "2026-03-01T00:00:00+00:00",
                        "workspaces": {
                            "feature/invalid": {
                                "branch": "feature/invalid",
                                "worktree_path": "/tmp/wt/invalid",
                                "tracked_remote": None,
                                "kind": "unsupported-kind",
                                "base_ref": "main",
                                "octopus_parents": [],
                                "created_at": "2026-03-01T00:00:00+00:00",
                                "updated_at": "2026-03-01T00:00:00+00:00",
                            }
                        },
                    }
                },
            },
            indent=2,
        )
    )

    manager = MetadataManager(path=metadata_path)

    with pytest.raises(ValueError, match="workspace kind must be either 'standard' or 'octopus'"):
        manager.read()


@pytest.mark.integration
def test_read_migrates_v0_schema_and_creates_backup(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    git_dir = repo_root / ".git"
    git_dir.mkdir()
    worktree_path = tmp_path / "repo-feature"
    worktree_path.mkdir()

    metadata_path = tmp_path / "workspaces.json"
    payload = _legacy_v0_payload(
        repo_key=str(git_dir.resolve(strict=False)),
        repo_root=repo_root.resolve(strict=False),
        worktree_path=worktree_path.resolve(strict=False),
    )
    original_text = json.dumps(payload, indent=2)
    metadata_path.write_text(original_text)

    manager = MetadataManager(path=metadata_path)
    migrated = manager.read()

    assert migrated.version == SCHEMA_VERSION
    raw_after = json.loads(metadata_path.read_text())
    assert raw_after["version"] == SCHEMA_VERSION

    backups = sorted(tmp_path.glob("workspaces.json.bak.*"))
    assert len(backups) == 1
    assert backups[0].read_text() == original_text


@pytest.mark.integration
def test_migration_preserves_workspace_fields(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    git_dir = repo_root / ".git"
    git_dir.mkdir()
    worktree_path = tmp_path / "repo-feature"
    worktree_path.mkdir()

    metadata_path = tmp_path / "workspaces.json"
    payload = _legacy_v0_payload(
        repo_key=str(git_dir.resolve(strict=False)),
        repo_root=repo_root.resolve(strict=False),
        worktree_path=worktree_path.resolve(strict=False),
    )
    metadata_path.write_text(json.dumps(payload, indent=2))

    manager = MetadataManager(path=metadata_path)
    migrated = manager.read()

    repo = migrated.repos[str(git_dir.resolve(strict=False))]
    workspace = repo.workspaces["feature/migrate"]
    assert repo.repo_root == repo_root.resolve(strict=False)
    assert workspace.branch == "feature/migrate"
    assert workspace.worktree_path == worktree_path.resolve(strict=False)
    assert workspace.base_ref == "main"
    assert workspace.kind == "standard"
    assert workspace.octopus_parents == ()
