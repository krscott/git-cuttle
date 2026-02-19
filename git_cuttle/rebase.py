from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal, cast

from git_cuttle.git_ops import GitCommandError, get_current_branch, pull_remote, run_git
from git_cuttle.workspace import (
    WorkspaceConfig,
    get_workspace,
    get_workspace_merge_commit,
    recompute_workspace_merge,
    save_workspace_ref,
)


@dataclass(frozen=True)
class RebaseState:
    operation: Literal["rebase", "pull"]
    workspace_name: str
    original_head: str
    target_branch: str


def _state_path() -> Path:
    git_dir = run_git(["rev-parse", "--git-common-dir"]).stdout.strip()
    return Path(git_dir) / "gitcuttle-rebase.json"


def save_rebase_state(state: RebaseState) -> None:
    with _state_path().open("w", encoding="utf-8") as fh:
        json.dump(asdict(state), fh, indent=2)


def load_rebase_state() -> RebaseState | None:
    try:
        with _state_path().open(encoding="utf-8") as fh:
            payload = json.load(fh)
    except FileNotFoundError:
        return None
    operation = str(payload["operation"])
    if operation not in {"rebase", "pull"}:
        raise RuntimeError(f"invalid rebase state operation: {operation}")
    return RebaseState(
        operation=cast(Literal["rebase", "pull"], operation),
        workspace_name=str(payload["workspace_name"]),
        original_head=str(payload["original_head"]),
        target_branch=str(payload["target_branch"]),
    )


def clear_rebase_state() -> None:
    path = _state_path()
    if path.exists():
        path.unlink()


def rebase_workspace_commits(
    workspace: WorkspaceConfig,
    operation: Literal["rebase", "pull"],
    continue_rebase: bool = False,
) -> None:
    if continue_rebase:
        resume_rebase()
        return

    merge_commit = get_workspace_merge_commit(workspace.name)
    if merge_commit is None:
        raise RuntimeError("workspace merge commit not found")

    temp_branch = f"gitcuttle-tmp-{workspace.name}"
    new_merge = recompute_workspace_merge(workspace, temp_branch)
    try:
        run_git(
            ["rebase", "--onto", new_merge, merge_commit, workspace.merge_branch],
            check=True,
        )
    except GitCommandError:
        save_rebase_state(
            RebaseState(
                operation=operation,
                workspace_name=workspace.name,
                original_head=merge_commit,
                target_branch=new_merge,
            )
        )
        raise
    finally:
        run_git(["branch", "-D", temp_branch], check=False)

    save_workspace_ref(workspace, new_merge)
    clear_rebase_state()


def resume_rebase() -> None:
    state = load_rebase_state()
    if state is None:
        raise RuntimeError("no gitcuttle rebase state to continue")

    run_git(["rebase", "--continue"])
    workspace = get_workspace(state.workspace_name)
    if workspace is None:
        raise RuntimeError(f"workspace not found: {state.workspace_name}")
    save_workspace_ref(workspace, state.target_branch)
    clear_rebase_state()


def update_workspace(workspace: WorkspaceConfig, continue_rebase: bool = False) -> None:
    if continue_rebase:
        rebase_workspace_commits(workspace, operation="pull", continue_rebase=True)
        return

    original_branch = get_current_branch()
    for branch in workspace.branches:
        run_git(["checkout", branch])
        pull_remote(branch)
    run_git(["checkout", original_branch])
    rebase_workspace_commits(workspace, operation="pull", continue_rebase=False)
