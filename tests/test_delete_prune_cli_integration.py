import os
import pathlib
import shutil
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


def _write_git_passthrough_with_update_ref_failure(
    *,
    script_path: pathlib.Path,
    branch: str,
    metadata_dir_to_lock: pathlib.Path | None = None,
) -> None:
    git_executable = shutil.which("git")
    assert git_executable is not None
    lock_metadata_snippet = ""
    if metadata_dir_to_lock is not None:
        lock_metadata_snippet = (
            f'if [ "${{1-}}" = "branch" ] && [ "${{3-}}" = "{branch}" ]; then\n'
            f'  chmod 500 "{metadata_dir_to_lock}"\n'
            "fi\n"
        )

    script_path.write_text(
        "#!/bin/sh\n"
        "set -eu\n"
        f"{lock_metadata_snippet}"
        f'if [ "${{1-}}" = "update-ref" ] && [ "${{2-}}" = "refs/heads/{branch}" ]; then\n'
        "  printf 'simulated update-ref failure\\n' >&2\n"
        "  exit 1\n"
        "fi\n"
        f'exec "{git_executable}" "$@"\n'
    )
    script_path.chmod(0o755)


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
        args=[
            "worktree",
            "add",
            str(extra_worktree),
            "feature/delete-worktree-rollback",
        ],
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
        'if [ "$1" = "pr" ] && [ "$2" = "list" ]; then\n'
        '  printf \'[{"state":"MERGED","isDraft":false,"title":"Merged","url":"https://example.com/pr/1"}]\'\n'
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
        args=[
            "worktree",
            "add",
            str(extra_worktree),
            "feature/prune-worktree-rollback",
        ],
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


@pytest.mark.integration
def test_cli_delete_reports_branch_recovery_when_branch_restore_rollback_fails(
    tmp_path: pathlib.Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)

    env = os.environ.copy()
    env["XDG_DATA_HOME"] = str(tmp_path / "xdg")

    branch = "feature/delete-branch-rollback"
    new_result = subprocess.run(
        ["gitcuttle", "new", "-b", branch, "--destination"],
        capture_output=True,
        text=True,
        cwd=repo,
        env=env,
    )
    assert new_result.returncode == 0

    metadata_dir = tmp_path / "xdg" / "gitcuttle"

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_git_passthrough_with_update_ref_failure(
        script_path=bin_dir / "git",
        branch=branch,
        metadata_dir_to_lock=metadata_dir,
    )
    env["PATH"] = f"{bin_dir}:{env['PATH']}"

    try:
        result = subprocess.run(
            ["gitcuttle", "delete", branch, "--force"],
            capture_output=True,
            text=True,
            cwd=repo,
            env=env,
        )
    finally:
        metadata_dir.chmod(0o700)

    assert result.returncode == 2
    assert "rollback failures:" in result.stderr
    assert "deterministic recovery commands:" in result.stderr
    assert f"git update-ref refs/heads/{branch} " in result.stderr


@pytest.mark.integration
def test_cli_prune_reports_branch_recovery_when_branch_restore_rollback_fails(
    tmp_path: pathlib.Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()

    branch = "feature/prune-branch-rollback"

    gh_path = bin_dir / "gh"
    gh_path.write_text(
        "#!/bin/sh\n"
        "set -eu\n"
        'if [ "$1" = "pr" ] && [ "$2" = "list" ]; then\n'
        '  printf \'[{"state":"MERGED","isDraft":false,"title":"Merged","url":"https://example.com/pr/1"}]\'\n'
        "  exit 0\n"
        "fi\n"
        "exit 1\n"
    )
    gh_path.chmod(0o755)

    env = os.environ.copy()
    env["XDG_DATA_HOME"] = str(tmp_path / "xdg")

    new_result = subprocess.run(
        ["gitcuttle", "new", "-b", branch, "--destination"],
        capture_output=True,
        text=True,
        cwd=repo,
        env=env,
    )
    assert new_result.returncode == 0
    _git(cwd=repo, args=["remote", "add", "origin", "https://github.com/acme/demo.git"])

    metadata_dir = tmp_path / "xdg" / "gitcuttle"
    _write_git_passthrough_with_update_ref_failure(
        script_path=bin_dir / "git",
        branch=branch,
        metadata_dir_to_lock=metadata_dir,
    )
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    try:
        result = subprocess.run(
            ["gitcuttle", "prune", "--force"],
            capture_output=True,
            text=True,
            cwd=repo,
            env=env,
        )
    finally:
        metadata_dir.chmod(0o700)

    assert result.returncode == 2
    assert "rollback failures:" in result.stderr
    assert "deterministic recovery commands:" in result.stderr
    assert f"git update-ref refs/heads/{branch} " in result.stderr


@pytest.mark.integration
def test_cli_delete_blocks_current_workspace_with_actionable_guidance(
    tmp_path: pathlib.Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)

    env = os.environ.copy()
    env["XDG_DATA_HOME"] = str(tmp_path / "xdg")

    new_result = subprocess.run(
        ["gitcuttle", "new", "-b", "feature/current", "--destination"],
        capture_output=True,
        text=True,
        cwd=repo,
        env=env,
    )
    assert new_result.returncode == 0

    workspace_path = pathlib.Path(new_result.stdout.strip())
    result = subprocess.run(
        ["gitcuttle", "delete", "feature/current"],
        capture_output=True,
        text=True,
        cwd=workspace_path,
        env=env,
    )

    assert result.returncode == 2
    assert "error[delete-blocked]: cannot delete the current workspace" in result.stderr
    assert "details: feature/current" in result.stderr
    assert "hint: switch to a different branch and rerun" in result.stderr


@pytest.mark.integration
def test_cli_delete_rejects_untracked_workspace_with_manual_git_guidance(
    tmp_path: pathlib.Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)

    env = os.environ.copy()
    env["XDG_DATA_HOME"] = str(tmp_path / "xdg")

    result = subprocess.run(
        ["gitcuttle", "delete", "feature/not-tracked"],
        capture_output=True,
        text=True,
        cwd=repo,
        env=env,
    )

    assert result.returncode == 2
    assert "error[workspace-not-tracked]: workspace is not tracked" in result.stderr
    assert "details: feature/not-tracked" in result.stderr
    assert "hint: run `git branch --list` to inspect local branches" in result.stderr
    assert "hint: if needed, delete manually with `git branch -D <branch>`" in result.stderr
