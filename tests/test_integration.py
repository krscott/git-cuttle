from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


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
        assert "no workspaces" in list_after_delete_result.stdout
