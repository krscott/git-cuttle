"""Validate README output snippets against real CLI behavior."""

import os
import pathlib
import subprocess

import pytest


def _init_repo(path: pathlib.Path) -> None:
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


@pytest.mark.integration
def test_readme_new_command_invocation_output(tmp_path: pathlib.Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    env = os.environ.copy()
    env["XDG_DATA_HOME"] = str(tmp_path / "xdg")

    result = subprocess.run(
        ["gitcuttle", "new", "-b", "feature/demo"],
        capture_output=True,
        text=True,
        cwd=repo,
        env=env,
    )

    assert result.returncode == 0
    assert "created workspace 'feature/demo' at" in result.stdout
    assert "hint: cd" in result.stdout
    assert result.stderr == ""


@pytest.mark.integration
def test_readme_destination_output_for_new(tmp_path: pathlib.Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    env = os.environ.copy()
    env["XDG_DATA_HOME"] = str(tmp_path / "xdg")

    result = subprocess.run(
        ["gitcuttle", "new", "-b", "feature/demo", "--destination"],
        capture_output=True,
        text=True,
        cwd=repo,
        env=env,
    )

    assert result.returncode == 0
    assert pathlib.Path(result.stdout.strip()).is_dir()
    assert result.stderr == ""


@pytest.mark.integration
def test_readme_outside_repo_error_snippet(tmp_path: pathlib.Path) -> None:
    result = subprocess.run(
        ["gitcuttle", "list"],
        capture_output=True,
        text=True,
        cwd=tmp_path,
    )

    assert result.returncode == 2
    stderr_lines = result.stderr.strip().splitlines()
    assert stderr_lines[0] == (
        "error[not-in-git-repo]: gitcuttle must be run from within a git repository"
    )
    assert stderr_lines[1] == (
        "hint: change to your repository root or one of its worktrees and retry"
    )


@pytest.mark.integration
def test_readme_in_progress_error_snippet(tmp_path: pathlib.Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)

    git_dir_result = subprocess.run(
        ["git", "rev-parse", "--git-dir"],
        capture_output=True,
        text=True,
        check=True,
        cwd=repo,
    )
    git_dir = pathlib.Path(git_dir_result.stdout.strip())
    if not git_dir.is_absolute():
        git_dir = (repo / git_dir).resolve(strict=False)
    (git_dir / "MERGE_HEAD").write_text("abc123\n")

    result = subprocess.run(
        ["gitcuttle", "list"],
        capture_output=True,
        text=True,
        cwd=repo,
    )

    assert result.returncode == 2
    stderr_lines = result.stderr.strip().splitlines()
    assert stderr_lines[0] == (
        "error[git-operation-in-progress]: repository has an in-progress git operation"
    )
    assert stderr_lines[1] == "details: detected state marker: MERGE_HEAD"
    assert (
        stderr_lines[2]
        == "hint: resolve or abort the git operation and rerun gitcuttle"
    )
