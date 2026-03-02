import os
import pathlib
import subprocess

import pytest


def _git(
    *, cwd: pathlib.Path, args: list[str], check: bool = True
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        check=check,
        cwd=cwd,
    )


def _init_repo(path: pathlib.Path) -> None:
    _git(cwd=path, args=["init", "-b", "main"])
    _git(cwd=path, args=["config", "user.name", "Test User"])
    _git(cwd=path, args=["config", "user.email", "test@example.com"])
    (path / "README.md").write_text("repo\n")
    _git(cwd=path, args=["add", "README.md"])
    _git(cwd=path, args=["commit", "-m", "init"])


@pytest.mark.integration
def test_cli_delete_reports_worktree_recovery_when_rollback_is_partial(
    tmp_path: pathlib.Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)

    env = os.environ.copy()
    env["XDG_DATA_HOME"] = str(tmp_path / "xdg")

    new_result = subprocess.run(
        ["gitcuttle", "new", "-b", "feature/delete-worktree-rollback", "--destination"],
        capture_output=True,
        text=True,
        cwd=repo,
        env=env,
    )
    assert new_result.returncode == 0
    workspace_path = pathlib.Path(new_result.stdout.strip())

    _git(cwd=workspace_path, args=["checkout", "--detach"])

    extra_worktree = tmp_path / "extra-delete"
    _git(
        cwd=repo,
        args=["worktree", "add", str(extra_worktree), "feature/delete-worktree-rollback"],
    )

    result = subprocess.run(
        ["gitcuttle", "delete", "feature/delete-worktree-rollback", "--force"],
        capture_output=True,
        text=True,
        cwd=repo,
        env=env,
    )

    assert result.returncode == 2
    assert (
        "error[transaction-rollback-failed]: operation failed and automatic rollback was partial"
        in result.stderr
    )
    assert "rollback failures:" in result.stderr
    assert "deterministic recovery commands:" in result.stderr
    assert (
        f"git worktree add {workspace_path} feature/delete-worktree-rollback"
        in result.stderr
    )


@pytest.mark.integration
def test_cli_prune_reports_worktree_recovery_when_rollback_is_partial(
    tmp_path: pathlib.Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gh_path = bin_dir / "gh"
    gh_path.write_text(
        "#!/bin/sh\n"
        "set -eu\n"
        "if [ \"$1\" = \"pr\" ] && [ \"$2\" = \"list\" ]; then\n"
        "  printf '[{\"state\":\"MERGED\",\"isDraft\":false,\"title\":\"Merged\",\"url\":\"https://example.com/pr/1\"}]'\n"
        "  exit 0\n"
        "fi\n"
        "exit 1\n"
    )
    gh_path.chmod(0o755)

    env = os.environ.copy()
    env["XDG_DATA_HOME"] = str(tmp_path / "xdg")
    env["PATH"] = f"{bin_dir}:{env['PATH']}"

    new_result = subprocess.run(
        ["gitcuttle", "new", "-b", "feature/prune-worktree-rollback", "--destination"],
        capture_output=True,
        text=True,
        cwd=repo,
        env=env,
    )
    assert new_result.returncode == 0
    workspace_path = pathlib.Path(new_result.stdout.strip())

    _git(cwd=workspace_path, args=["checkout", "--detach"])
    _git(cwd=repo, args=["remote", "add", "origin", "https://github.com/acme/demo.git"])

    extra_worktree = tmp_path / "extra-prune"
    _git(
        cwd=repo,
        args=["worktree", "add", str(extra_worktree), "feature/prune-worktree-rollback"],
    )

    result = subprocess.run(
        ["gitcuttle", "prune", "--force"],
        capture_output=True,
        text=True,
        cwd=repo,
        env=env,
    )

    assert result.returncode == 2
    assert (
        "error[transaction-rollback-failed]: operation failed and automatic rollback was partial"
        in result.stderr
    )
    assert "rollback failures:" in result.stderr
    assert "deterministic recovery commands:" in result.stderr
    assert (
        f"git worktree add {workspace_path} feature/prune-worktree-rollback"
        in result.stderr
    )
