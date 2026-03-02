import pathlib
import subprocess

import pytest

import git_cuttle.orchestrator as orchestrator_module
from git_cuttle.lib import Options
from git_cuttle.metadata_manager import MetadataManager
from git_cuttle.orchestrator import command_requires_auto_tracking, run


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


class StubTracker:
    def __init__(self) -> None:
        self.calls: list[pathlib.Path] = []

    def ensure_repo_tracked(self, *, cwd: pathlib.Path) -> None:
        self.calls.append(cwd)


def _noop_dispatch(
    *,
    command_name: str,
    opts: Options,
    cwd: pathlib.Path,
    metadata_manager: object,
) -> None:
    _ = command_name
    _ = opts
    _ = cwd
    _ = metadata_manager


def test_command_requires_auto_tracking_for_mutating_commands() -> None:
    assert command_requires_auto_tracking("new")
    assert command_requires_auto_tracking("delete")
    assert command_requires_auto_tracking("prune")
    assert command_requires_auto_tracking("update")
    assert command_requires_auto_tracking("absorb")


def test_command_requires_auto_tracking_ignores_non_mutating_commands() -> None:
    assert not command_requires_auto_tracking("list")
    assert not command_requires_auto_tracking("unknown")


def test_run_tracks_repo_for_mutating_command(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    tracker = StubTracker()

    monkeypatch.setattr(orchestrator_module, "_dispatch_command", _noop_dispatch)

    run(
        Options(branch="feature/demo"),
        cwd=repo,
        metadata_manager=tracker,
        command_name="delete",
    )

    assert tracker.calls == [repo]


def test_run_skips_tracking_for_non_mutating_command(tmp_path: pathlib.Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    tracker = StubTracker()

    run(Options(), cwd=repo, metadata_manager=tracker, command_name="list")

    assert tracker.calls == []


def test_non_mutating_command_never_creates_tracking_entries(
    tmp_path: pathlib.Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    metadata_path = tmp_path / "workspaces.json"
    manager = MetadataManager(path=metadata_path)

    run(Options(), cwd=repo, metadata_manager=manager, command_name="list")
    run(Options(), cwd=repo, metadata_manager=manager, command_name="list")

    assert not metadata_path.exists()
