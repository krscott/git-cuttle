import os
import subprocess
from pathlib import Path

import pytest

from git_cuttle.metadata_manager import (
    MetadataManager,
    RepoMetadata,
    WorkspaceMetadata,
    WorkspacesMetadata,
)


def _git(
    *, cwd: Path, args: list[str], check: bool = True
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        check=check,
        capture_output=True,
        text=True,
        cwd=cwd,
    )


def _run_cli(
    *, cwd: Path, xdg_data_home: Path, args: list[str]
) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["XDG_DATA_HOME"] = str(xdg_data_home)
    return subprocess.run(
        ["gitcuttle", *args],
        check=False,
        capture_output=True,
        text=True,
        cwd=cwd,
        env=env,
    )


def _init_repo(path: Path) -> None:
    _git(cwd=path, args=["init", "-b", "main"])
    _git(cwd=path, args=["config", "user.name", "Test User"])
    _git(cwd=path, args=["config", "user.email", "test@example.com"])
    (path / "README.md").write_text("hello\n")
    _git(cwd=path, args=["add", "README.md"])
    _git(cwd=path, args=["commit", "-m", "init"])


def _canonical_git_dir(repo: Path) -> Path:
    git_dir = _git(cwd=repo, args=["rev-parse", "--git-common-dir"]).stdout.strip()
    candidate = Path(git_dir)
    if candidate.is_absolute():
        return candidate.resolve(strict=False)
    return (repo / candidate).resolve(strict=False)


def _write_repo_metadata(
    *,
    metadata_path: Path,
    repo_root: Path,
    default_remote: str | None,
    workspace: WorkspaceMetadata,
) -> None:
    manager = MetadataManager(path=metadata_path)
    canonical_git_dir = _canonical_git_dir(repo_root)
    record = RepoMetadata(
        git_dir=canonical_git_dir,
        repo_root=repo_root.resolve(strict=False),
        default_remote=default_remote,
        tracked_at="2026-03-02T00:00:00Z",
        updated_at="2026-03-02T00:00:00Z",
        workspaces={workspace.branch: workspace},
    )
    manager.write(
        WorkspacesMetadata(
            version=1,
            repos={str(canonical_git_dir): record},
        )
    )


def _delete_case(
    *, tmp_path: Path, from_worktree: bool
) -> subprocess.CompletedProcess[str]:
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    _init_repo(repo)

    xdg_data_home = tmp_path / "xdg"
    target_result = _run_cli(
        cwd=repo,
        xdg_data_home=xdg_data_home,
        args=["new", "-b", "feature/delete-target", "--destination"],
    )
    context_result = _run_cli(
        cwd=repo,
        xdg_data_home=xdg_data_home,
        args=["new", "-b", "feature/context", "--destination"],
    )
    assert target_result.returncode == 0
    assert context_result.returncode == 0
    target_workspace = Path(target_result.stdout.strip())
    context_workspace = Path(context_result.stdout.strip())

    invocation_cwd = context_workspace if from_worktree else repo
    result = _run_cli(
        cwd=invocation_cwd,
        xdg_data_home=xdg_data_home,
        args=["delete", "feature/delete-target", "--force"],
    )

    assert result.returncode == 0
    assert not target_workspace.exists()
    branch_check = _git(
        cwd=repo,
        args=["show-ref", "--verify", "--quiet", "refs/heads/feature/delete-target"],
        check=False,
    )
    assert branch_check.returncode != 0

    metadata = MetadataManager(
        path=xdg_data_home / "gitcuttle" / "workspaces.json"
    ).read()
    tracked_repo = next(iter(metadata.repos.values()))
    assert "feature/delete-target" not in tracked_repo.workspaces
    assert "feature/context" in tracked_repo.workspaces
    return result


def _prune_case(
    *, tmp_path: Path, from_worktree: bool
) -> subprocess.CompletedProcess[str]:
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    _init_repo(repo)

    xdg_data_home = tmp_path / "xdg"
    target_result = _run_cli(
        cwd=repo,
        xdg_data_home=xdg_data_home,
        args=["new", "-b", "feature/prune-target", "--destination"],
    )
    context_result = _run_cli(
        cwd=repo,
        xdg_data_home=xdg_data_home,
        args=["new", "-b", "feature/context", "--destination"],
    )
    assert target_result.returncode == 0
    assert context_result.returncode == 0
    target_workspace = Path(target_result.stdout.strip())
    context_workspace = Path(context_result.stdout.strip())

    _git(cwd=target_workspace, args=["checkout", "--detach"])
    _git(cwd=repo, args=["branch", "-D", "feature/prune-target"])

    invocation_cwd = context_workspace if from_worktree else repo
    result = _run_cli(
        cwd=invocation_cwd,
        xdg_data_home=xdg_data_home,
        args=["prune", "--force"],
    )

    assert result.returncode == 0
    assert not target_workspace.exists()
    branch_check = _git(
        cwd=repo,
        args=["show-ref", "--verify", "--quiet", "refs/heads/feature/prune-target"],
        check=False,
    )
    assert branch_check.returncode != 0

    metadata = MetadataManager(
        path=xdg_data_home / "gitcuttle" / "workspaces.json"
    ).read()
    tracked_repo = next(iter(metadata.repos.values()))
    assert "feature/prune-target" not in tracked_repo.workspaces
    assert "feature/context" in tracked_repo.workspaces
    return result


def _clone_local_remote(*, tmp_path: Path) -> tuple[Path, Path]:
    source = tmp_path / "source"
    source.mkdir(parents=True)
    _init_repo(source)

    bare_remote = tmp_path / "remote.git"
    _git(cwd=source, args=["clone", "--bare", str(source), str(bare_remote)])

    local = tmp_path / "local"
    _git(cwd=tmp_path, args=["clone", str(bare_remote), str(local)])
    _git(cwd=local, args=["config", "user.name", "Test User"])
    _git(cwd=local, args=["config", "user.email", "test@example.com"])

    return bare_remote, local


def _update_case(
    *, tmp_path: Path, from_worktree: bool
) -> subprocess.CompletedProcess[str]:
    bare_remote, local = _clone_local_remote(tmp_path=tmp_path)

    _git(cwd=local, args=["checkout", "-b", "feature/update-parity"])
    (local / "feature.txt").write_text("local a\n")
    _git(cwd=local, args=["add", "feature.txt"])
    _git(cwd=local, args=["commit", "-m", "local a"])
    _git(cwd=local, args=["push", "-u", "origin", "feature/update-parity"])

    upstream_writer = tmp_path / "upstream-writer"
    _git(cwd=tmp_path, args=["clone", str(bare_remote), str(upstream_writer)])
    _git(cwd=upstream_writer, args=["config", "user.name", "Test User"])
    _git(cwd=upstream_writer, args=["config", "user.email", "test@example.com"])
    _git(cwd=upstream_writer, args=["checkout", "feature/update-parity"])
    (upstream_writer / "upstream.txt").write_text("upstream b\n")
    _git(cwd=upstream_writer, args=["add", "upstream.txt"])
    _git(cwd=upstream_writer, args=["commit", "-m", "upstream b"])
    _git(cwd=upstream_writer, args=["push", "origin", "feature/update-parity"])
    upstream_head = _git(
        cwd=upstream_writer,
        args=["rev-parse", "--verify", "HEAD"],
    ).stdout.strip()

    (local / "local.txt").write_text("local c\n")
    _git(cwd=local, args=["add", "local.txt"])
    _git(cwd=local, args=["commit", "-m", "local c"])

    invocation_cwd = local
    if from_worktree:
        _git(cwd=local, args=["checkout", "main"])
        invocation_cwd = tmp_path / "update-worktree"
        _git(
            cwd=local,
            args=["worktree", "add", str(invocation_cwd), "feature/update-parity"],
        )

    xdg_data_home = tmp_path / "xdg"
    metadata_path = xdg_data_home / "gitcuttle" / "workspaces.json"
    _write_repo_metadata(
        metadata_path=metadata_path,
        repo_root=local,
        default_remote="origin",
        workspace=WorkspaceMetadata(
            branch="feature/update-parity",
            worktree_path=invocation_cwd,
            tracked_remote="origin",
            kind="standard",
            base_ref="main",
            octopus_parents=(),
            created_at="2026-03-02T00:00:00Z",
            updated_at="2026-03-02T00:00:00Z",
        ),
    )

    result = _run_cli(cwd=invocation_cwd, xdg_data_home=xdg_data_home, args=["update"])

    assert result.returncode == 0
    rebased_parent = _git(
        cwd=invocation_cwd,
        args=["show", "-s", "--format=%P", "HEAD"],
    ).stdout.strip()
    assert rebased_parent == upstream_head
    return result


def _setup_octopus_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    _init_repo(repo)

    _git(cwd=repo, args=["checkout", "-b", "release"])
    (repo / "release.txt").write_text("release v1\n")
    _git(cwd=repo, args=["add", "release.txt"])
    _git(cwd=repo, args=["commit", "-m", "release v1"])

    _git(cwd=repo, args=["checkout", "main"])
    (repo / "main.txt").write_text("main v1\n")
    _git(cwd=repo, args=["add", "main.txt"])
    _git(cwd=repo, args=["commit", "-m", "main v1"])

    _git(cwd=repo, args=["checkout", "-b", "integration/main-release", "main"])
    _git(
        cwd=repo,
        args=["merge", "--no-ff", "-m", "Create octopus workspace", "release"],
    )
    return repo


def _absorb_case(
    *, tmp_path: Path, from_worktree: bool
) -> subprocess.CompletedProcess[str]:
    repo = _setup_octopus_repo(tmp_path)
    (repo / "release-only.txt").write_text("r1\n")
    _git(cwd=repo, args=["add", "release-only.txt"])
    _git(cwd=repo, args=["commit", "-m", "release-only"])

    invocation_cwd = repo
    if from_worktree:
        _git(cwd=repo, args=["checkout", "main"])
        invocation_cwd = tmp_path / "absorb-worktree"
        _git(
            cwd=repo,
            args=["worktree", "add", str(invocation_cwd), "integration/main-release"],
        )

    xdg_data_home = tmp_path / "xdg"
    metadata_path = xdg_data_home / "gitcuttle" / "workspaces.json"
    _write_repo_metadata(
        metadata_path=metadata_path,
        repo_root=repo,
        default_remote=None,
        workspace=WorkspaceMetadata(
            branch="integration/main-release",
            worktree_path=invocation_cwd,
            tracked_remote=None,
            kind="octopus",
            base_ref="main",
            octopus_parents=("main", "release"),
            created_at="2026-03-02T00:00:00Z",
            updated_at="2026-03-02T00:00:00Z",
        ),
    )

    result = _run_cli(
        cwd=invocation_cwd,
        xdg_data_home=xdg_data_home,
        args=["absorb", "release"],
    )

    assert result.returncode == 0
    release_head_subject = _git(
        cwd=repo, args=["log", "--format=%s", "-n", "1", "release"]
    ).stdout.strip()
    assert release_head_subject == "release-only"
    return result


@pytest.mark.integration
def test_cli_delete_has_repo_root_worktree_parity(tmp_path: Path) -> None:
    from_root = _delete_case(tmp_path=tmp_path / "root", from_worktree=False)
    from_worktree = _delete_case(tmp_path=tmp_path / "worktree", from_worktree=True)

    assert from_root.returncode == from_worktree.returncode
    assert from_root.stdout == from_worktree.stdout
    assert from_root.stderr == from_worktree.stderr


@pytest.mark.integration
def test_cli_prune_has_repo_root_worktree_parity(tmp_path: Path) -> None:
    from_root = _prune_case(tmp_path=tmp_path / "root", from_worktree=False)
    from_worktree = _prune_case(tmp_path=tmp_path / "worktree", from_worktree=True)

    assert from_root.returncode == from_worktree.returncode
    assert from_root.stdout == from_worktree.stdout
    assert from_root.stderr == from_worktree.stderr


@pytest.mark.integration
def test_cli_update_has_repo_root_worktree_parity(tmp_path: Path) -> None:
    from_root = _update_case(tmp_path=tmp_path / "root", from_worktree=False)
    from_worktree = _update_case(tmp_path=tmp_path / "worktree", from_worktree=True)

    assert from_root.returncode == from_worktree.returncode
    assert from_root.stdout == from_worktree.stdout
    assert from_root.stderr == from_worktree.stderr


@pytest.mark.integration
def test_cli_absorb_has_repo_root_worktree_parity(tmp_path: Path) -> None:
    from_root = _absorb_case(tmp_path=tmp_path / "root", from_worktree=False)
    from_worktree = _absorb_case(tmp_path=tmp_path / "worktree", from_worktree=True)

    assert from_root.returncode == from_worktree.returncode
    assert from_root.stdout == from_worktree.stdout
    assert from_root.stderr == from_worktree.stderr
