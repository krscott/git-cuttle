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


def _init_repo(path: Path) -> None:
    _git(cwd=path, args=["init", "-b", "main"])
    _git(cwd=path, args=["config", "user.name", "Test User"])
    _git(cwd=path, args=["config", "user.email", "test@example.com"])
    (path / "README.md").write_text("hello\n")
    _git(cwd=path, args=["add", "README.md"])
    _git(cwd=path, args=["commit", "-m", "init"])


def _canonical_git_dir(repo: Path) -> Path:
    git_dir = _git(cwd=repo, args=["rev-parse", "--git-dir"]).stdout.strip()
    candidate = Path(git_dir)
    if candidate.is_absolute():
        return candidate.resolve(strict=False)
    return (repo / candidate).resolve(strict=False)


def _write_repo_metadata(
    *,
    metadata_path: Path,
    repo: Path,
    default_remote: str | None,
    workspace: WorkspaceMetadata,
) -> None:
    manager = MetadataManager(path=metadata_path)
    canonical_git_dir = _canonical_git_dir(repo)
    repo_root = repo.resolve(strict=False)
    record = RepoMetadata(
        git_dir=canonical_git_dir,
        repo_root=repo_root,
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


def _workspace_metadata(*, branch: str, worktree: Path) -> WorkspaceMetadata:
    return WorkspaceMetadata(
        branch=branch,
        worktree_path=worktree,
        tracked_remote=None,
        kind="octopus",
        base_ref="main",
        octopus_parents=("main", "release"),
        created_at="2026-03-02T00:00:00Z",
        updated_at="2026-03-02T00:00:00Z",
    )


def _setup_octopus_repo(tmp_path: Path) -> tuple[Path, WorkspaceMetadata]:
    repo = tmp_path / "repo"
    repo.mkdir()
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
        cwd=repo, args=["merge", "--no-ff", "-m", "Create octopus workspace", "release"]
    )
    return repo, _workspace_metadata(branch="integration/main-release", worktree=repo)


def _run_absorb(
    *,
    cwd: Path,
    xdg_data_home: Path,
    args: list[str],
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["XDG_DATA_HOME"] = str(xdg_data_home)
    return subprocess.run(
        ["gitcuttle", "absorb", *args],
        check=False,
        capture_output=True,
        text=True,
        input=input_text,
        cwd=cwd,
        env=env,
    )


@pytest.mark.integration
def test_cli_absorb_explicit_target_moves_commits_to_parent(tmp_path: Path) -> None:
    repo, workspace = _setup_octopus_repo(tmp_path)

    (repo / "release-only.txt").write_text("r1\n")
    _git(cwd=repo, args=["add", "release-only.txt"])
    _git(cwd=repo, args=["commit", "-m", "release-only"])

    old_head = _git(
        cwd=repo, args=["rev-parse", "--verify", "integration/main-release"]
    ).stdout.strip()

    xdg_data_home = tmp_path / "xdg"
    metadata_path = xdg_data_home / "gitcuttle" / "workspaces.json"
    _write_repo_metadata(
        metadata_path=metadata_path, repo=repo, default_remote=None, workspace=workspace
    )

    result = _run_absorb(cwd=repo, xdg_data_home=xdg_data_home, args=["release"])

    assert result.returncode == 0
    assert result.stdout == "absorbed 1 commit(s) from integration/main-release\n"
    new_head = _git(
        cwd=repo, args=["rev-parse", "--verify", "integration/main-release"]
    ).stdout.strip()
    assert new_head != old_head
    merge_parents = _git(
        cwd=repo,
        args=["show", "-s", "--format=%P", "integration/main-release"],
    ).stdout.split()
    assert len(merge_parents) == 2

    release_head = _git(cwd=repo, args=["rev-parse", "--verify", "release"]).stdout.strip()
    assert merge_parents[1] == release_head
    release_head_subject = _git(
        cwd=repo, args=["log", "--format=%s", "-n", "1", "release"]
    ).stdout.strip()
    assert release_head_subject == "release-only"

    unique_after_absorb = _git(
        cwd=repo,
        args=[
            "rev-list",
            "--reverse",
            "integration/main-release",
            "--not",
            "main",
            "release",
        ],
    ).stdout.splitlines()
    assert len(unique_after_absorb) == 1


@pytest.mark.integration
def test_cli_absorb_interactive_mode_uses_selected_parent(tmp_path: Path) -> None:
    repo, workspace = _setup_octopus_repo(tmp_path)

    (repo / "main-only.txt").write_text("m1\n")
    _git(cwd=repo, args=["add", "main-only.txt"])
    _git(cwd=repo, args=["commit", "-m", "main-only"])

    xdg_data_home = tmp_path / "xdg"
    metadata_path = xdg_data_home / "gitcuttle" / "workspaces.json"
    _write_repo_metadata(
        metadata_path=metadata_path, repo=repo, default_remote=None, workspace=workspace
    )

    result = _run_absorb(
        cwd=repo, xdg_data_home=xdg_data_home, args=["-i"], input_text="1\n"
    )

    assert result.returncode == 0
    assert "choose parent branch for" in result.stdout
    assert "absorbed 1 commit(s) from integration/main-release" in result.stdout
    main_head_subject = _git(
        cwd=repo, args=["log", "--format=%s", "-n", "1", "main"]
    ).stdout.strip()
    assert main_head_subject == "main-only"


@pytest.mark.integration
def test_cli_absorb_heuristic_mode_reports_ambiguity(tmp_path: Path) -> None:
    repo, workspace = _setup_octopus_repo(tmp_path)

    (repo / "README.md").write_text("ambiguous\n")
    _git(cwd=repo, args=["add", "README.md"])
    _git(cwd=repo, args=["commit", "-m", "touch shared file"])

    xdg_data_home = tmp_path / "xdg"
    metadata_path = xdg_data_home / "gitcuttle" / "workspaces.json"
    _write_repo_metadata(
        metadata_path=metadata_path, repo=repo, default_remote=None, workspace=workspace
    )

    result = _run_absorb(cwd=repo, xdg_data_home=xdg_data_home, args=[])

    assert result.returncode == 2
    assert (
        "error[absorb-target-uncertain]: could not infer a high-confidence absorb target"
        in result.stderr
    )
    assert (
        "hint: rerun with an explicit parent branch or interactive mode (-i)"
        in result.stderr
    )


@pytest.mark.integration
def test_cli_absorb_fails_when_current_workspace_is_non_octopus(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    _git(cwd=repo, args=["checkout", "-b", "feature/standard"])

    xdg_data_home = tmp_path / "xdg"
    metadata_path = xdg_data_home / "gitcuttle" / "workspaces.json"
    _write_repo_metadata(
        metadata_path=metadata_path,
        repo=repo,
        default_remote=None,
        workspace=WorkspaceMetadata(
            branch="feature/standard",
            worktree_path=repo,
            tracked_remote=None,
            kind="standard",
            base_ref="main",
            octopus_parents=(),
            created_at="2026-03-02T00:00:00Z",
            updated_at="2026-03-02T00:00:00Z",
        ),
    )

    result = _run_absorb(cwd=repo, xdg_data_home=xdg_data_home, args=[])

    assert result.returncode == 2
    assert "error[invalid-workspace-kind]: absorb requires octopus workspace metadata" in result.stderr
    assert "details: feature/standard" in result.stderr


@pytest.mark.integration
def test_cli_absorb_rolls_back_touched_refs_and_cleans_backup_refs(tmp_path: Path) -> None:
    repo, workspace = _setup_octopus_repo(tmp_path)

    (repo / "shared.txt").write_text("from octopus\n")
    _git(cwd=repo, args=["add", "shared.txt"])
    _git(cwd=repo, args=["commit", "-m", "octopus change"])

    _git(cwd=repo, args=["checkout", "main"])
    (repo / "shared.txt").write_text("from main\n")
    _git(cwd=repo, args=["add", "shared.txt"])
    _git(cwd=repo, args=["commit", "-m", "main conflicting change"])

    _git(cwd=repo, args=["checkout", workspace.branch])

    before_main_oid = _git(
        cwd=repo,
        args=["rev-parse", "--verify", "refs/heads/main"],
    ).stdout.strip()
    before_release_oid = _git(
        cwd=repo,
        args=["rev-parse", "--verify", "refs/heads/release"],
    ).stdout.strip()
    before_octopus_oid = _git(
        cwd=repo,
        args=["rev-parse", "--verify", f"refs/heads/{workspace.branch}"],
    ).stdout.strip()

    xdg_data_home = tmp_path / "xdg"
    metadata_path = xdg_data_home / "gitcuttle" / "workspaces.json"
    _write_repo_metadata(
        metadata_path=metadata_path,
        repo=repo,
        default_remote=None,
        workspace=workspace,
    )

    result = _run_absorb(cwd=repo, xdg_data_home=xdg_data_home, args=[])

    assert result.returncode == 2
    assert (
        "error[absorb-cherry-pick-failed]: failed to cherry-pick commit onto target parent"
        in result.stderr
    )

    after_main_oid = _git(
        cwd=repo,
        args=["rev-parse", "--verify", "refs/heads/main"],
    ).stdout.strip()
    after_release_oid = _git(
        cwd=repo,
        args=["rev-parse", "--verify", "refs/heads/release"],
    ).stdout.strip()
    after_octopus_oid = _git(
        cwd=repo,
        args=["rev-parse", "--verify", f"refs/heads/{workspace.branch}"],
    ).stdout.strip()

    assert after_main_oid == before_main_oid
    assert after_release_oid == before_release_oid
    assert after_octopus_oid == before_octopus_oid

    backup_refs = _git(
        cwd=repo,
        args=["for-each-ref", "--format=%(refname)", "refs/gitcuttle/txn"],
    ).stdout.strip()
    assert backup_refs == ""


@pytest.mark.integration
def test_cli_absorb_reports_deterministic_recovery_when_rollback_is_partial(
    tmp_path: Path,
) -> None:
    repo, workspace = _setup_octopus_repo(tmp_path)

    (repo / "release-only.txt").write_text("r1\n")
    _git(cwd=repo, args=["add", "release-only.txt"])
    _git(cwd=repo, args=["commit", "-m", "release-only"])

    hooks_dir = tmp_path / "hooks"
    hooks_dir.mkdir()
    post_checkout = hooks_dir / "post-checkout"
    post_checkout.write_text(
        "#!/bin/sh\n"
        "set -eu\n"
        "if [ -f .git/gitcuttle_absorb_hook_done ]; then\n"
        "  exit 0\n"
        "fi\n"
        "branch=$(git rev-parse --abbrev-ref HEAD)\n"
        "if [ \"$branch\" != \"release\" ]; then\n"
        "  exit 0\n"
        "fi\n"
        "touch .git/gitcuttle_absorb_hook_done\n"
        "for ref in $(git for-each-ref --format='%(refname)' refs/gitcuttle/txn); do\n"
        "  git update-ref -d \"$ref\"\n"
        "done\n"
        "printf 'hook divergence\\n' >> release.txt\n"
        "git add release.txt\n"
        "git commit -m 'hook diverge' >/dev/null 2>&1 || true\n"
    )
    post_checkout.chmod(0o755)
    _git(cwd=repo, args=["config", "core.hooksPath", str(hooks_dir)])

    xdg_data_home = tmp_path / "xdg"
    metadata_path = xdg_data_home / "gitcuttle" / "workspaces.json"
    _write_repo_metadata(
        metadata_path=metadata_path,
        repo=repo,
        default_remote=None,
        workspace=workspace,
    )

    result = _run_absorb(cwd=repo, xdg_data_home=xdg_data_home, args=["release"])

    assert result.returncode == 2
    assert (
        "error[transaction-rollback-failed]: operation failed and automatic rollback was partial"
        in result.stderr
    )
    assert "rollback failures:" in result.stderr
    assert "deterministic recovery commands:" in result.stderr
    assert (
        f"git checkout {workspace.branch} && git reset --hard refs/gitcuttle/txn/"
        in result.stderr
    )
