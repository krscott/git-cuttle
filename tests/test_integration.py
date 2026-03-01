from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def _git_output(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


@pytest.mark.integration
def test_cli_new_list_status() -> None:
    project_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{project_root}:{env.get('PYTHONPATH', '')}"

    with tempfile.TemporaryDirectory() as tmp_dir:
        repo = Path(tmp_dir) / "repo"
        repo.mkdir()
        _git(repo, "init", "-b", "main")
        _git(repo, "config", "user.email", "test@example.com")
        _git(repo, "config", "user.name", "Test User")
        (repo / "base.txt").write_text("base\n", encoding="utf-8")
        _git(repo, "add", ".")
        _git(repo, "commit", "-m", "base")

        _git(repo, "checkout", "-b", "feature-a")
        (repo / "a.txt").write_text("a\n", encoding="utf-8")
        _git(repo, "add", ".")
        _git(repo, "commit", "-m", "a")

        _git(repo, "checkout", "main")
        _git(repo, "checkout", "-b", "feature-b")
        (repo / "b.txt").write_text("b\n", encoding="utf-8")
        _git(repo, "add", ".")
        _git(repo, "commit", "-m", "b")
        _git(repo, "checkout", "main")

        new_result = subprocess.run(
            [
                sys.executable,
                "-m",
                "git_cuttle",
                "new",
                "feature-a",
                "feature-b",
                "--name",
                "ws",
            ],
            cwd=repo,
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )
        assert new_result.returncode == 0

        list_result = subprocess.run(
            [sys.executable, "-m", "git_cuttle", "list"],
            cwd=repo,
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )
        assert list_result.returncode == 0
        assert "ws" in list_result.stdout

        status_result = subprocess.run(
            [sys.executable, "-m", "git_cuttle", "status"],
            cwd=repo,
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )
        assert status_result.returncode == 0
        assert "workspace: ws" in status_result.stdout

        delete_result = subprocess.run(
            [sys.executable, "-m", "git_cuttle", "delete"],
            cwd=repo,
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )
        assert delete_result.returncode == 0
        assert "deleted workspace metadata: ws" in delete_result.stdout

        list_after_delete_result = subprocess.run(
            [sys.executable, "-m", "git_cuttle", "list"],
            cwd=repo,
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )
        assert list_after_delete_result.returncode == 0
        assert "no tracked workspaces or worktrees" in list_after_delete_result.stdout


@pytest.mark.integration
def test_cli_worktree_print_path_success_and_failure() -> None:
    project_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{project_root}:{env.get('PYTHONPATH', '')}"

    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        repo = root / "repo"
        xdg_data_home = root / "xdg-data"
        repo.mkdir()
        _git(repo, "init", "-b", "main")
        _git(repo, "config", "user.email", "test@example.com")
        _git(repo, "config", "user.name", "Test User")
        (repo / "base.txt").write_text("base\n", encoding="utf-8")
        _git(repo, "add", ".")
        _git(repo, "commit", "-m", "base")

        _git(repo, "checkout", "-b", "feature-a")
        (repo / "a.txt").write_text("a\n", encoding="utf-8")
        _git(repo, "add", ".")
        _git(repo, "commit", "-m", "a")
        _git(repo, "checkout", "main")

        run_env = {**env, "XDG_DATA_HOME": str(xdg_data_home)}
        success_result = subprocess.run(
            [
                sys.executable,
                "-m",
                "git_cuttle",
                "worktree",
                "feature-a",
                "--print-path",
            ],
            cwd=repo,
            check=False,
            capture_output=True,
            text=True,
            env=run_env,
        )

        assert success_result.returncode == 0
        assert success_result.stderr == ""
        created_path = Path(success_result.stdout.strip())
        assert created_path.is_absolute()
        assert created_path.exists()

        reuse_result = subprocess.run(
            [
                sys.executable,
                "-m",
                "git_cuttle",
                "worktree",
                "feature-a",
                "--print-path",
            ],
            cwd=repo,
            check=False,
            capture_output=True,
            text=True,
            env=run_env,
        )
        assert reuse_result.returncode == 0
        assert Path(reuse_result.stdout.strip()) == created_path

        list_result = subprocess.run(
            [sys.executable, "-m", "git_cuttle", "list"],
            cwd=repo,
            check=False,
            capture_output=True,
            text=True,
            env=run_env,
        )
        assert list_result.returncode == 0
        assert f"feature-a [branch]: path={created_path}" in list_result.stdout

        status_result = subprocess.run(
            [sys.executable, "-m", "git_cuttle", "status"],
            cwd=created_path,
            check=False,
            capture_output=True,
            text=True,
            env=run_env,
        )
        assert status_result.returncode == 0
        assert "type: tracked worktree" in status_result.stdout
        assert str(created_path) in status_result.stdout

        failure_result = subprocess.run(
            [sys.executable, "-m", "git_cuttle", "worktree", "main", "--print-path"],
            cwd=repo,
            check=False,
            capture_output=True,
            text=True,
            env=run_env,
        )

        assert failure_result.returncode == 1
        assert failure_result.stdout == ""
        assert "switch to another branch first" in failure_result.stderr

        delete_result = subprocess.run(
            [sys.executable, "-m", "git_cuttle", "delete", "feature-a"],
            cwd=repo,
            check=False,
            capture_output=True,
            text=True,
            env=run_env,
        )
        assert delete_result.returncode == 0
        assert "deleted tracked worktree: feature-a" in delete_result.stdout
        assert not created_path.exists()


@pytest.mark.integration
def test_cli_worktree_remote_fallback_prefers_origin() -> None:
    project_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{project_root}:{env.get('PYTHONPATH', '')}"

    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        repo = root / "repo"
        remote = root / "remote.git"
        xdg_data_home = root / "xdg-data"

        repo.mkdir()
        _git(repo, "init", "-b", "main")
        _git(repo, "config", "user.email", "test@example.com")
        _git(repo, "config", "user.name", "Test User")
        (repo / "base.txt").write_text("base\n", encoding="utf-8")
        _git(repo, "add", ".")
        _git(repo, "commit", "-m", "base")

        remote.mkdir()
        _git(remote, "init", "--bare")
        _git(repo, "remote", "add", "origin", str(remote))
        _git(repo, "push", "-u", "origin", "main")

        _git(repo, "checkout", "-b", "remote-feature")
        (repo / "remote.txt").write_text("remote\n", encoding="utf-8")
        _git(repo, "add", ".")
        _git(repo, "commit", "-m", "remote feature")
        _git(repo, "push", "-u", "origin", "remote-feature")
        _git(repo, "checkout", "main")
        _git(repo, "branch", "-D", "remote-feature")
        _git(repo, "fetch", "origin")

        run_env = {**env, "XDG_DATA_HOME": str(xdg_data_home)}
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "git_cuttle",
                "worktree",
                "remote-feature",
                "--print-path",
            ],
            cwd=repo,
            check=False,
            capture_output=True,
            text=True,
            env=run_env,
        )

        assert result.returncode == 0
        worktree_path = Path(result.stdout.strip())
        assert worktree_path.exists()
        assert _git_output(worktree_path, "branch", "--show-current") == "remote-feature"


@pytest.mark.integration
def test_cli_worktree_multi_branch_tracks_and_deletes() -> None:
    project_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{project_root}:{env.get('PYTHONPATH', '')}"

    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        repo = root / "repo"
        xdg_data_home = root / "xdg-data"
        repo.mkdir()
        _git(repo, "init", "-b", "main")
        _git(repo, "config", "user.email", "test@example.com")
        _git(repo, "config", "user.name", "Test User")
        (repo / "base.txt").write_text("base\n", encoding="utf-8")
        _git(repo, "add", ".")
        _git(repo, "commit", "-m", "base")

        _git(repo, "checkout", "-b", "feature-a")
        (repo / "a.txt").write_text("a\n", encoding="utf-8")
        _git(repo, "add", ".")
        _git(repo, "commit", "-m", "a")

        _git(repo, "checkout", "main")
        _git(repo, "checkout", "-b", "feature-b")
        (repo / "b.txt").write_text("b\n", encoding="utf-8")
        _git(repo, "add", ".")
        _git(repo, "commit", "-m", "b")
        _git(repo, "checkout", "main")

        run_env = {**env, "XDG_DATA_HOME": str(xdg_data_home)}
        worktree_result = subprocess.run(
            [
                sys.executable,
                "-m",
                "git_cuttle",
                "worktree",
                "feature-a",
                "feature-b",
                "--name",
                "ws",
                "--print-path",
            ],
            cwd=repo,
            check=False,
            capture_output=True,
            text=True,
            env=run_env,
        )
        assert worktree_result.returncode == 0
        worktree_path = Path(worktree_result.stdout.strip())
        assert worktree_path.exists()
        assert _git_output(worktree_path, "branch", "--show-current") == "ws"
        assert _git_output(repo, "branch", "--show-current") == "main"

        list_result = subprocess.run(
            [sys.executable, "-m", "git_cuttle", "list"],
            cwd=repo,
            check=False,
            capture_output=True,
            text=True,
            env=run_env,
        )
        assert list_result.returncode == 0
        assert "ws [workspace]" in list_result.stdout
        assert str(worktree_path) in list_result.stdout

        status_result = subprocess.run(
            [sys.executable, "-m", "git_cuttle", "status"],
            cwd=worktree_path,
            check=False,
            capture_output=True,
            text=True,
            env=run_env,
        )
        assert status_result.returncode == 0
        assert "workspace: ws" in status_result.stdout
        assert str(worktree_path) in status_result.stdout

        delete_result = subprocess.run(
            [sys.executable, "-m", "git_cuttle", "delete", "ws"],
            cwd=repo,
            check=False,
            capture_output=True,
            text=True,
            env=run_env,
        )
        assert delete_result.returncode == 0
        assert "deleted workspace and worktree: ws" in delete_result.stdout
        assert not worktree_path.exists()

        list_after_delete = subprocess.run(
            [sys.executable, "-m", "git_cuttle", "list"],
            cwd=repo,
            check=False,
            capture_output=True,
            text=True,
            env=run_env,
        )
        assert list_after_delete.returncode == 0
        assert "no tracked workspaces or worktrees" in list_after_delete.stdout
