from __future__ import annotations

import subprocess
from pathlib import Path

from pytest import MonkeyPatch

from git_cuttle.git_ops import (
    create_octopus_merge,
    get_current_branch,
    get_merge_base,
    run_git,
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


def test_create_octopus_merge(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
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
    merge_commit = create_octopus_merge(["feature-a", "feature-b"], "workspace-ab")

    assert get_current_branch() == "workspace-ab"
    assert run_git(["rev-parse", "HEAD"]).stdout.strip() == merge_commit


def test_get_merge_base(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    repo = _init_repo(tmp_path)
    monkeypatch.chdir(repo)
    base = run_git(["rev-parse", "HEAD"]).stdout.strip()

    _git(repo, "checkout", "-b", "feature-a")
    (repo / "a.txt").write_text("a\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "a")

    _git(repo, "checkout", "main")
    _git(repo, "checkout", "-b", "feature-b")
    (repo / "b.txt").write_text("b\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "b")

    assert get_merge_base(["feature-a", "feature-b"]) == base
