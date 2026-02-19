from __future__ import annotations

import subprocess
from pathlib import Path

from pytest import MonkeyPatch

from git_cuttle.git_ops import run_git
from git_cuttle.rebase import rebase_workspace_commits
from git_cuttle.workspace import create_workspace


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")
    (repo / "base.txt").write_text("base\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "base")
    return repo


def test_absorb_rebases_post_merge_commits(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    repo = _init_repo(tmp_path)
    monkeypatch.chdir(repo)

    _git(repo, "checkout", "-b", "feature-a")
    (repo / "a.txt").write_text("a1\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "a1")

    _git(repo, "checkout", "main")
    _git(repo, "checkout", "-b", "feature-b")
    (repo / "b.txt").write_text("b1\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "b1")

    _git(repo, "checkout", "main")
    workspace = create_workspace(["feature-a", "feature-b"], name="workspace-ab")
    (repo / "workspace.txt").write_text("wip\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "workspace")

    _git(repo, "checkout", "feature-a")
    (repo / "a2.txt").write_text("a2\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "a2")
    _git(repo, "checkout", "workspace-ab")

    rebase_workspace_commits(workspace, operation="rebase")

    log = run_git(["log", "--oneline", "-n", "5"]).stdout
    assert "workspace" in log
    assert (repo / "workspace.txt").exists()
