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


def _run_cli(*, cwd: Path, args: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
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
    legacy_payload = {
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

    assert result.returncode == 0

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

    assert result.returncode == 0

    metadata_path = home_dir / ".local" / "share" / "gitcuttle" / "workspaces.json"
    assert metadata_path.exists()

    payload = json.loads(metadata_path.read_text())
    assert payload["version"] == 1
    assert payload["repos"]
