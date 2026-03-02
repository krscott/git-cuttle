"""Black-box integration tests for CLI subcommand architecture."""

import json
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
def test_cli_help_lists_subcommands() -> None:
    result = subprocess.run(["gitcuttle", "--help"], capture_output=True, text=True)

    assert result.returncode == 0
    assert "new" in result.stdout
    assert "list" in result.stdout
    assert "delete" in result.stdout
    assert "prune" in result.stdout
    assert "update" in result.stdout
    assert "absorb" in result.stdout


@pytest.mark.integration
def test_cli_invalid_arguments_show_actionable_guidance() -> None:
    result = subprocess.run(
        ["gitcuttle", "delete"],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "error[invalid-arguments]: invalid command arguments" in result.stderr
    assert "the following arguments are required: branch" in result.stderr
    assert "hint: run `gitcuttle --help` to view valid usage" in result.stderr


@pytest.mark.integration
def test_cli_new_and_destination_invocation_paths(tmp_path: pathlib.Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    env = os.environ.copy()
    env["XDG_DATA_HOME"] = str(tmp_path / "xdg")

    destination = subprocess.run(
        ["gitcuttle", "new", "-b", "feature/demo", "--destination"],
        capture_output=True,
        text=True,
        cwd=repo,
        env=env,
    )
    invoked = subprocess.run(
        ["gitcuttle", "new", "-b", "feature/demo-2"],
        capture_output=True,
        text=True,
        cwd=repo,
        env=env,
    )

    assert destination.returncode == 0
    destination_path = pathlib.Path(destination.stdout.strip())
    assert destination_path.is_dir()

    assert invoked.returncode == 0
    assert "created workspace 'feature/demo-2' at" in invoked.stdout
    assert "hint: cd" in invoked.stdout


@pytest.mark.integration
def test_cli_per_command_invocation_paths(tmp_path: pathlib.Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    env = os.environ.copy()
    env["XDG_DATA_HOME"] = str(tmp_path / "xdg")

    new_result = subprocess.run(
        ["gitcuttle", "new", "-b", "feature/demo", "--destination"],
        capture_output=True,
        text=True,
        cwd=repo,
        env=env,
    )
    assert new_result.returncode == 0

    list_result = subprocess.run(
        ["gitcuttle", "list"],
        capture_output=True,
        text=True,
        cwd=repo,
        env=env,
    )
    assert list_result.returncode == 0
    assert "REPO" in list_result.stdout
    assert "feature/demo" in list_result.stdout

    delete_result = subprocess.run(
        ["gitcuttle", "delete", "feature/demo", "--dry-run"],
        capture_output=True,
        text=True,
        cwd=repo,
        env=env,
    )
    assert delete_result.returncode == 2
    assert "error[no-upstream]" in delete_result.stderr

    prune_result = subprocess.run(
        ["gitcuttle", "prune", "--dry-run"],
        capture_output=True,
        text=True,
        cwd=repo,
        env=env,
    )
    assert prune_result.returncode == 0
    assert "Dry-run plan for `prune`:" in prune_result.stdout


@pytest.mark.integration
def test_cli_json_invocation_paths(tmp_path: pathlib.Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    env = os.environ.copy()
    env["XDG_DATA_HOME"] = str(tmp_path / "xdg")

    new_result = subprocess.run(
        ["gitcuttle", "new", "-b", "feature/demo", "--destination"],
        capture_output=True,
        text=True,
        cwd=repo,
        env=env,
    )
    assert new_result.returncode == 0

    list_result = subprocess.run(
        ["gitcuttle", "list", "--json"],
        capture_output=True,
        text=True,
        cwd=repo,
        env=env,
    )
    delete_result = subprocess.run(
        ["gitcuttle", "delete", "feature/demo", "--dry-run", "--json"],
        capture_output=True,
        text=True,
        cwd=repo,
        env=env,
    )
    prune_result = subprocess.run(
        ["gitcuttle", "prune", "--dry-run", "--json"],
        capture_output=True,
        text=True,
        cwd=repo,
        env=env,
    )

    assert list_result.returncode == 0
    list_payload = json.loads(list_result.stdout)
    assert list_payload["workspaces"]
    assert delete_result.returncode == 2
    assert "error[no-upstream]" in delete_result.stderr
    assert prune_result.returncode == 0
    prune_payload = json.loads(prune_result.stdout)
    assert prune_payload["command"] == "prune"
    assert prune_payload["dry_run"] is True


@pytest.mark.integration
def test_cli_errors_outside_git_repo(tmp_path: pathlib.Path) -> None:
    result = subprocess.run(
        ["gitcuttle", "list"],
        capture_output=True,
        text=True,
        cwd=tmp_path,
    )
    assert result.returncode != 0
    assert (
        "error[not-in-git-repo]: gitcuttle must be run from within a git repository"
        in result.stderr
    )
    assert (
        "hint: change to your repository root or one of its worktrees and retry"
        in result.stderr
    )


@pytest.mark.integration
def test_cli_blocks_when_git_operation_is_in_progress(tmp_path: pathlib.Path) -> None:
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

    assert result.returncode != 0
    assert (
        "error[git-operation-in-progress]: repository has an in-progress git operation"
        in result.stderr
    )
    assert "details: detected state marker: MERGE_HEAD" in result.stderr
    assert (
        "hint: resolve or abort the git operation and rerun gitcuttle" in result.stderr
    )
