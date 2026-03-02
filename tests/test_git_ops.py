from __future__ import annotations

import subprocess
from pathlib import Path

from pytest import MonkeyPatch

from git_cuttle.git_ops import (
    create_octopus_merge,
    get_current_branch,
    get_merge_base,
    list_remote_branch_matches,
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


def test_list_remote_branch_matches_uses_exact_branch_part(
    monkeypatch: MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def _fake_run_git(
        args: list[str], check: bool = True
    ) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        assert check is True
        if args == ["remote"]:
            return subprocess.CompletedProcess(
                args=["git", *args],
                returncode=0,
                stdout="origin\nfork\n",
                stderr="",
            )
        assert args == ["for-each-ref", "--format=%(refname:short)", "refs/remotes"]
        return subprocess.CompletedProcess(
            args=["git", *args],
            returncode=0,
            stdout=(
                "origin/HEAD\n"
                "origin/feature/x\n"
                "origin/team/feature/x\n"
                "fork/feature/x\n"
            ),
            stderr="",
        )

    monkeypatch.setattr("git_cuttle.git_ops.run_git", _fake_run_git)

    assert list_remote_branch_matches("feature/x") == [
        "fork/feature/x",
        "origin/feature/x",
    ]
    assert calls == [
        ["remote"],
        ["for-each-ref", "--format=%(refname:short)", "refs/remotes"],
    ]


def test_list_remote_branch_matches_supports_remote_names_with_slash(
    monkeypatch: MonkeyPatch,
) -> None:
    def _fake_run_git(
        args: list[str], check: bool = True
    ) -> subprocess.CompletedProcess[str]:
        assert check is True
        if args == ["remote"]:
            return subprocess.CompletedProcess(
                args=["git", *args],
                returncode=0,
                stdout="origin\nfoo/bar\n",
                stderr="",
            )

        assert args == ["for-each-ref", "--format=%(refname:short)", "refs/remotes"]
        return subprocess.CompletedProcess(
            args=["git", *args],
            returncode=0,
            stdout=(
                "origin/HEAD\n" "origin/feat\n" "foo/bar/feat\n" "foo/bar/nested/feat\n"
            ),
            stderr="",
        )

    monkeypatch.setattr("git_cuttle.git_ops.run_git", _fake_run_git)

    assert list_remote_branch_matches("feat") == ["foo/bar/feat", "origin/feat"]
