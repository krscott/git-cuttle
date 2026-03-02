import json
import os
import subprocess
from pathlib import Path

import pytest


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


def _run_cli(
    *, cwd: Path, args: list[str], env: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["gitcuttle", *args],
        check=False,
        capture_output=True,
        text=True,
        cwd=cwd,
        env=env,
    )


@pytest.mark.integration
def test_cli_list_does_not_create_tracking_metadata(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)

    xdg_data_home = tmp_path / "xdg"
    env = dict(os.environ)
    env["XDG_DATA_HOME"] = str(xdg_data_home)

    result = _run_cli(cwd=repo, args=["list"], env=env)

    assert result.returncode == 0
    assert not (xdg_data_home / "gitcuttle" / "workspaces.json").exists()


@pytest.mark.integration
def test_cli_list_cache_refresh_never_creates_tracking_metadata(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)

    xdg_data_home = tmp_path / "xdg"
    env = dict(os.environ)
    env["XDG_DATA_HOME"] = str(xdg_data_home)

    first = _run_cli(cwd=repo, args=["list"], env=env)
    second = _run_cli(cwd=repo, args=["list"], env=env)

    assert first.returncode == 0
    assert second.returncode == 0
    assert not (xdg_data_home / "gitcuttle" / "workspaces.json").exists()


@pytest.mark.integration
def test_cli_mutating_command_migrates_existing_metadata(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)

    git_dir = subprocess.run(
        ["git", "rev-parse", "--git-dir"],
        check=True,
        capture_output=True,
        text=True,
        cwd=repo,
    ).stdout.strip()
    canonical_git_dir = (repo / git_dir).resolve(strict=False)

    xdg_data_home = tmp_path / "xdg"
    metadata_dir = xdg_data_home / "gitcuttle"
    metadata_dir.mkdir(parents=True)
    metadata_path = metadata_dir / "workspaces.json"
    legacy_payload: dict[str, object] = {
        "version": 0,
        "repos": {
            str(canonical_git_dir): {
                "git_dir": str(canonical_git_dir),
                "repo_root": str(repo.resolve(strict=False)),
                "default_remote": None,
                "tracked_at": "2026-03-01T00:00:00+00:00",
                "updated_at": "2026-03-01T00:00:00+00:00",
                "workspaces": {},
            }
        },
    }
    original_text = json.dumps(legacy_payload, indent=2)
    metadata_path.write_text(original_text)

    env = dict(os.environ)
    env["XDG_DATA_HOME"] = str(xdg_data_home)

    result = _run_cli(cwd=repo, args=["update"], env=env)

    assert result.returncode == 2
    assert (
        "error[workspace-not-tracked]: current branch is not a tracked workspace"
        in result.stderr
    )

    migrated = json.loads(metadata_path.read_text())
    assert migrated["version"] == 1
    assert str(canonical_git_dir) in migrated["repos"]

    backups = sorted(metadata_dir.glob("workspaces.json.bak.*"))
    assert len(backups) == 1
    assert backups[0].read_text() == original_text


@pytest.mark.integration
def test_cli_mutating_command_uses_home_fallback_path(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)

    home_dir = tmp_path / "home"
    home_dir.mkdir()

    env = dict(os.environ)
    env.pop("XDG_DATA_HOME", None)
    env["HOME"] = str(home_dir)

    result = _run_cli(cwd=repo, args=["update"], env=env)

    assert result.returncode == 2
    assert (
        "error[workspace-not-tracked]: current branch is not a tracked workspace"
        in result.stderr
    )

    metadata_path = home_dir / ".local" / "share" / "gitcuttle" / "workspaces.json"
    assert metadata_path.exists()

    payload = json.loads(metadata_path.read_text())
    assert payload["version"] == 1
    assert payload["repos"]


@pytest.mark.integration
def test_cli_mutating_commands_from_worktree_use_single_repo_identity(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)

    xdg_data_home = tmp_path / "xdg"
    env = dict(os.environ)
    env["XDG_DATA_HOME"] = str(xdg_data_home)

    first_new = _run_cli(
        cwd=repo,
        args=["new", "-b", "feature/from-root", "--destination"],
        env=env,
    )
    assert first_new.returncode == 0
    first_workspace = Path(first_new.stdout.strip())

    second_new = _run_cli(
        cwd=first_workspace,
        args=["new", "-b", "feature/from-worktree", "--destination"],
        env=env,
    )
    assert second_new.returncode == 0

    metadata_path = xdg_data_home / "gitcuttle" / "workspaces.json"
    payload = json.loads(metadata_path.read_text())
    assert len(payload["repos"]) == 1
    tracked_repo = next(iter(payload["repos"].values()))
    assert sorted(tracked_repo["workspaces"].keys()) == [
        "feature/from-root",
        "feature/from-worktree",
    ]

    list_from_repo = _run_cli(cwd=repo, args=["list"], env=env)
    list_from_worktree = _run_cli(cwd=first_workspace, args=["list"], env=env)
    assert list_from_repo.returncode == 0
    assert list_from_worktree.returncode == 0
    assert "feature/from-root" in list_from_repo.stdout
    assert "feature/from-worktree" in list_from_repo.stdout
    assert "feature/from-root" in list_from_worktree.stdout
    assert "feature/from-worktree" in list_from_worktree.stdout
