import hashlib
from pathlib import Path

import pytest

from git_cuttle.workspace_paths import (
    derive_branch_dir,
    derive_repo_id,
    derive_workspace_path,
)


def test_derive_repo_id_uses_slug_plus_hash() -> None:
    git_dir = Path("/repos/My Repo/.git")

    repo_id = derive_repo_id(git_dir)

    expected_hash = hashlib.sha256(str(git_dir).encode("utf-8")).hexdigest()[:8]
    assert repo_id == f"my-repo-{expected_hash}"


def test_derive_workspace_path_uses_xdg_data_home(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", "/tmp/xdg")
    git_dir = Path("/repos/demo/.git")

    workspace_path = derive_workspace_path(
        git_dir=git_dir,
        branch="Feature/Awesome_Work",
    )

    expected_hash = hashlib.sha256(str(git_dir).encode("utf-8")).hexdigest()[:8]
    assert workspace_path == Path(
        f"/tmp/xdg/gitcuttle/demo-{expected_hash}/feature-awesome_work"
    )


def test_collision_appends_deterministic_suffix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", "/tmp/xdg")
    git_dir = Path("/repos/demo/.git")
    branch = "feature/a"

    workspace_path = derive_workspace_path(
        git_dir=git_dir,
        branch=branch,
        sibling_branches=["feature-a"],
    )

    expected_hash = hashlib.sha256(str(git_dir).encode("utf-8")).hexdigest()[:8]
    expected_suffix = hashlib.sha256(branch.encode("utf-8")).hexdigest()[:6]
    assert workspace_path == Path(
        f"/tmp/xdg/gitcuttle/demo-{expected_hash}/feature-a-{expected_suffix}"
    )


def test_derive_branch_dir_is_stable_and_non_empty() -> None:
    assert derive_branch_dir("feat///alpha") == "feat-alpha"
    assert derive_branch_dir("...") == "workspace"
