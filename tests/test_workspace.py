from __future__ import annotations

import subprocess
from pathlib import Path

from pytest import MonkeyPatch

from git_cuttle.workspace import (
    create_workspace,
    delete_workspace,
    get_workspace,
    list_workspaces,
)


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


def test_workspace_crud(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    repo = _init_repo(tmp_path)
    monkeypatch.chdir(repo)

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
    workspace = create_workspace(["feature-a", "feature-b"], name="workspace-ab")

    assert workspace.name == "workspace-ab"
    assert get_workspace() is not None
    assert [w.name for w in list_workspaces()] == ["workspace-ab"]

    delete_workspace("workspace-ab")
    assert list_workspaces() == []
