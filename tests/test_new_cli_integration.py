import hashlib
import os
import pathlib
import re
import subprocess

import pytest

from git_cuttle.metadata_manager import MetadataManager


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
def test_cli_new_standard_from_repo_root_creates_workspace_and_metadata(
    tmp_path: pathlib.Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)

    env = os.environ.copy()
    env["XDG_DATA_HOME"] = str(tmp_path / "xdg")

    result = subprocess.run(
        ["gitcuttle", "new", "-b", "feature/root", "--destination"],
        capture_output=True,
        text=True,
        cwd=repo,
        env=env,
    )

    assert result.returncode == 0
    destination = pathlib.Path(result.stdout.strip())
    assert destination.is_dir()

    metadata = MetadataManager(
        path=tmp_path / "xdg" / "gitcuttle" / "workspaces.json"
    ).read()
    tracked_repo = next(iter(metadata.repos.values()))
    assert "feature/root" in tracked_repo.workspaces


@pytest.mark.integration
def test_cli_new_octopus_from_worktree_context_creates_workspace(
    tmp_path: pathlib.Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)

    subprocess.run(["git", "checkout", "-b", "release"], check=True, cwd=repo)
    (repo / "release.txt").write_text("release\n")
    subprocess.run(["git", "add", "release.txt"], check=True, cwd=repo)
    subprocess.run(["git", "commit", "-m", "release"], check=True, cwd=repo)

    subprocess.run(["git", "checkout", "main"], check=True, cwd=repo)
    subprocess.run(["git", "checkout", "-b", "hotfix"], check=True, cwd=repo)
    (repo / "hotfix.txt").write_text("hotfix\n")
    subprocess.run(["git", "add", "hotfix.txt"], check=True, cwd=repo)
    subprocess.run(["git", "commit", "-m", "hotfix"], check=True, cwd=repo)
    subprocess.run(["git", "checkout", "main"], check=True, cwd=repo)

    existing_worktree = tmp_path / "existing-release"
    subprocess.run(
        ["git", "worktree", "add", str(existing_worktree), "release"],
        check=True,
        cwd=repo,
    )

    env = os.environ.copy()
    env["XDG_DATA_HOME"] = str(tmp_path / "xdg")

    result = subprocess.run(
        [
            "gitcuttle",
            "new",
            "main",
            "release",
            "hotfix",
            "-b",
            "integration/from-worktree",
            "--destination",
        ],
        capture_output=True,
        text=True,
        cwd=existing_worktree,
        env=env,
    )

    assert result.returncode == 0
    destination = pathlib.Path(result.stdout.strip())
    assert destination.is_dir()

    metadata = MetadataManager(
        path=tmp_path / "xdg" / "gitcuttle" / "workspaces.json"
    ).read()
    tracked_repo = next(iter(metadata.repos.values()))
    assert "integration/from-worktree" in tracked_repo.workspaces
    assert tracked_repo.workspaces["integration/from-worktree"].kind == "octopus"


@pytest.mark.integration
def test_cli_new_without_branch_generates_workspace_branch_name(
    tmp_path: pathlib.Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)

    env = os.environ.copy()
    env["XDG_DATA_HOME"] = str(tmp_path / "xdg")

    result = subprocess.run(
        ["gitcuttle", "new", "--destination"],
        capture_output=True,
        text=True,
        cwd=repo,
        env=env,
    )

    assert result.returncode == 0
    destination = pathlib.Path(result.stdout.strip())
    assert destination.is_dir()

    metadata = MetadataManager(
        path=tmp_path / "xdg" / "gitcuttle" / "workspaces.json"
    ).read()
    tracked_repo = next(iter(metadata.repos.values()))
    generated_branch = next(iter(tracked_repo.workspaces.keys()))
    assert re.fullmatch(r"workspace-[k-z]{8}", generated_branch) is not None


@pytest.mark.integration
def test_cli_new_without_branch_generates_unique_names_across_runs(
    tmp_path: pathlib.Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)

    env = os.environ.copy()
    env["XDG_DATA_HOME"] = str(tmp_path / "xdg")

    first = subprocess.run(
        ["gitcuttle", "new", "--destination"],
        capture_output=True,
        text=True,
        cwd=repo,
        env=env,
    )
    second = subprocess.run(
        ["gitcuttle", "new", "--destination"],
        capture_output=True,
        text=True,
        cwd=repo,
        env=env,
    )

    assert first.returncode == 0
    assert second.returncode == 0

    metadata = MetadataManager(
        path=tmp_path / "xdg" / "gitcuttle" / "workspaces.json"
    ).read()
    tracked_repo = next(iter(metadata.repos.values()))
    generated_branches = list(tracked_repo.workspaces.keys())

    assert len(generated_branches) == 2
    assert len(set(generated_branches)) == 2
    assert all(
        re.fullmatch(r"workspace-[k-z]{8}", branch) is not None
        for branch in generated_branches
    )


@pytest.mark.integration
def test_cli_new_collision_uses_deterministic_paths_and_unsanitized_metadata_keys(
    tmp_path: pathlib.Path,
) -> None:
    repo = tmp_path / "My Repo"
    repo.mkdir()
    _init_repo(repo)

    env = os.environ.copy()
    env["XDG_DATA_HOME"] = str(tmp_path / "xdg")

    first_branch = "feature/a"
    second_branch = "feature-a"

    first = subprocess.run(
        ["gitcuttle", "new", "-b", first_branch, "--destination"],
        capture_output=True,
        text=True,
        cwd=repo,
        env=env,
    )
    second = subprocess.run(
        ["gitcuttle", "new", "-b", second_branch, "--destination"],
        capture_output=True,
        text=True,
        cwd=repo,
        env=env,
    )

    assert first.returncode == 0
    assert second.returncode == 0

    first_destination = pathlib.Path(first.stdout.strip())
    second_destination = pathlib.Path(second.stdout.strip())
    expected_repo_hash = hashlib.sha256(
        str((repo / ".git").resolve(strict=False)).encode("utf-8")
    ).hexdigest()[:8]
    expected_repo_dir = tmp_path / "xdg" / "gitcuttle" / f"my-repo-{expected_repo_hash}"
    expected_suffix = hashlib.sha256(second_branch.encode("utf-8")).hexdigest()[:6]

    assert first_destination.is_dir()
    assert second_destination.is_dir()
    assert first_destination.parent == expected_repo_dir
    assert first_destination.parent == second_destination.parent
    assert first_destination.name == "feature-a"
    assert second_destination.name == f"feature-a-{expected_suffix}"

    metadata = MetadataManager(
        path=tmp_path / "xdg" / "gitcuttle" / "workspaces.json"
    ).read()
    tracked_repo = next(iter(metadata.repos.values()))

    assert set(tracked_repo.workspaces.keys()) == {first_branch, second_branch}
    assert tracked_repo.workspaces[first_branch].branch == first_branch
    assert tracked_repo.workspaces[second_branch].branch == second_branch
    assert tracked_repo.workspaces[first_branch].worktree_path == first_destination
    assert tracked_repo.workspaces[second_branch].worktree_path == second_destination


@pytest.mark.integration
def test_cli_new_invalid_base_ref_shows_actionable_hint(tmp_path: pathlib.Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)

    env = os.environ.copy()
    env["XDG_DATA_HOME"] = str(tmp_path / "xdg")

    result = subprocess.run(
        ["gitcuttle", "new", "missing/base", "-b", "feature/invalid-base"],
        capture_output=True,
        text=True,
        cwd=repo,
        env=env,
    )

    assert result.returncode == 2
    assert "error[invalid-base-ref]: base ref does not exist" in result.stderr
    assert "details: missing/base" in result.stderr
    assert "hint: pass a valid local branch, tag, or commit" in result.stderr


@pytest.mark.integration
def test_cli_new_reports_worktree_recovery_when_rollback_is_partial(
    tmp_path: pathlib.Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)

    xdg_data_home = tmp_path / "xdg"
    env = os.environ.copy()
    env["XDG_DATA_HOME"] = str(xdg_data_home)

    metadata_manager = MetadataManager(
        path=xdg_data_home / "gitcuttle" / "workspaces.json"
    )
    metadata_manager.ensure_repo_tracked(cwd=repo)

    hooks_dir = tmp_path / "hooks"
    hooks_dir.mkdir()
    marker_path = tmp_path / "new-rollback-hook-done"
    metadata_dir = xdg_data_home / "gitcuttle"
    post_checkout = hooks_dir / "post-checkout"
    post_checkout.write_text(
        "#!/bin/sh\n"
        "set -eu\n"
        f"if [ -f '{marker_path}' ]; then\n"
        "  exit 0\n"
        "fi\n"
        f"touch '{marker_path}'\n"
        'git worktree lock "$PWD"\n'
        f"chmod 500 '{metadata_dir}'\n"
    )
    post_checkout.chmod(0o755)
    subprocess.run(
        ["git", "config", "core.hooksPath", str(hooks_dir)],
        check=True,
        cwd=repo,
    )

    result = subprocess.run(
        ["gitcuttle", "new", "-b", "feature/new-worktree-rollback", "--destination"],
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
    assert "git worktree unlock " in result.stderr
    assert "git worktree remove --force " in result.stderr
