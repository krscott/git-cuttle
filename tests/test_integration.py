"""Black-box integration tests for the CLI using subprocess.

These tests invoke the CLI as a real process to verify the end-to-end user experience.
"""

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
def test_cli_basic_argument() -> None:
    """Test CLI with a basic name argument."""
    result = subprocess.run(
        ["gitcuttle", "Alice"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "Hello, Alice!" in result.stdout


@pytest.mark.integration
def test_cli_default_name() -> None:
    """Test CLI with no arguments uses default name."""
    result = subprocess.run(
        ["gitcuttle"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "Hello, World!" in result.stdout


@pytest.mark.integration
def test_cli_destination_outputs_path_only() -> None:
    result = subprocess.run(
        ["gitcuttle", "--destination"],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert result.stdout.strip() == str(pathlib.Path.cwd().resolve())
    assert result.stderr == ""


@pytest.mark.integration
def test_cli_verbose_flag() -> None:
    """Test CLI with --verbose flag shows debug output."""
    result = subprocess.run(
        ["gitcuttle", "--verbose", "Bob"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "Hello, Bob!" in result.stdout
    assert "Greeting user..." in result.stderr


@pytest.mark.integration
def test_cli_verbose_short_flag() -> None:
    """Test CLI with -v short flag shows debug output."""
    result = subprocess.run(
        ["gitcuttle", "-v", "Charlie"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "Hello, Charlie!" in result.stdout
    assert "Greeting user..." in result.stderr


@pytest.mark.integration
def test_cli_verbose_env_var() -> None:
    """Test CLI with GITCUTTLE_VERBOSE environment variable."""
    env = os.environ.copy()
    env["GITCUTTLE_VERBOSE"] = "1"
    result = subprocess.run(
        ["gitcuttle", "David"],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0
    assert "Hello, David!" in result.stdout
    assert "Greeting user..." in result.stderr


@pytest.mark.integration
def test_cli_flag_overrides_env_var() -> None:
    """Test that command line flag works even when env var is not set."""
    env = os.environ.copy()
    # Ensure the env var is not set
    env.pop("GITCUTTLE_VERBOSE", None)
    result = subprocess.run(
        ["gitcuttle", "--verbose", "Eve"],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0
    assert "Hello, Eve!" in result.stdout
    assert "Greeting user..." in result.stderr


@pytest.mark.integration
def test_cli_errors_outside_git_repo(tmp_path: pathlib.Path) -> None:
    """Test CLI fails with guidance when run outside a git repository."""
    result = subprocess.run(
        ["gitcuttle", "Frank"],
        capture_output=True,
        text=True,
        cwd=tmp_path,
    )
    assert result.returncode != 0
    assert "error[not-in-git-repo]: gitcuttle must be run from within a git repository" in result.stderr
    assert "hint: change to your repository root or one of its worktrees and retry" in result.stderr


@pytest.mark.integration
def test_cli_behaves_same_from_repo_root_and_worktree(tmp_path: pathlib.Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _init_repo(repo_root)

    worktree_dir = tmp_path / "repo-feature"
    subprocess.run(
        ["git", "worktree", "add", "-b", "feature", str(worktree_dir)],
        check=True,
        cwd=repo_root,
    )

    root_result = subprocess.run(
        ["gitcuttle", "Grace"],
        capture_output=True,
        text=True,
        cwd=repo_root,
    )
    worktree_result = subprocess.run(
        ["gitcuttle", "Grace"],
        capture_output=True,
        text=True,
        cwd=worktree_dir,
    )

    assert root_result.returncode == 0
    assert worktree_result.returncode == 0
    assert root_result.stdout == worktree_result.stdout
    assert "Hello, Grace!" in root_result.stdout
