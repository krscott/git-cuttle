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
