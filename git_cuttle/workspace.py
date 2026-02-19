from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from git_cuttle.git_ops import (
    create_octopus_merge,
    get_current_branch,
    get_head_commit,
    get_merge_base,
    run_git,
)


@dataclass(frozen=True)
class WorkspaceConfig:
    name: str
    branches: list[str]
    base_branch: str
    merge_branch: str


def _git_dir() -> Path:
    return Path(run_git(["rev-parse", "--git-common-dir"]).stdout.strip())


def _workspace_dir() -> Path:
    return _git_dir() / "gitcuttle" / "workspaces"


def _workspace_config_path(name: str) -> Path:
    return _workspace_dir() / f"{name}.json"


def _workspace_ref_path(name: str) -> Path:
    return _git_dir() / "refs" / "gitcuttle" / name


def generate_workspace_name(branches: list[str]) -> str:
    slug = "-".join(branches)
    stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    return f"workspace-{slug}-{stamp}"


def save_workspace_ref(config: WorkspaceConfig, commit_sha: str) -> None:
    config_path = _workspace_config_path(config.name)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(asdict(config), indent=2), encoding="utf-8")

    ref_path = _workspace_ref_path(config.name)
    ref_path.parent.mkdir(parents=True, exist_ok=True)
    ref_path.write_text(f"{commit_sha}\n", encoding="utf-8")


def get_workspace_merge_commit(name: str) -> str | None:
    ref_path = _workspace_ref_path(name)
    if not ref_path.exists():
        return None
    return ref_path.read_text(encoding="utf-8").strip()


def create_workspace(branches: list[str], name: str | None = None) -> WorkspaceConfig:
    if len(branches) < 2:
        raise ValueError("workspace requires at least two branches")

    workspace_name = name or generate_workspace_name(branches)
    base_branch = get_merge_base(branches)
    merge_commit = create_octopus_merge(branches, workspace_name)
    config = WorkspaceConfig(
        name=workspace_name,
        branches=branches,
        base_branch=base_branch,
        merge_branch=workspace_name,
    )
    save_workspace_ref(config, merge_commit)
    return config


def _load_workspace(path: Path) -> WorkspaceConfig:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return WorkspaceConfig(
        name=str(payload["name"]),
        branches=[str(branch) for branch in payload["branches"]],
        base_branch=str(payload["base_branch"]),
        merge_branch=str(payload["merge_branch"]),
    )


def get_workspace(branch_name: str | None = None) -> WorkspaceConfig | None:
    target_branch = branch_name or get_current_branch()
    config_path = _workspace_config_path(target_branch)
    if config_path.exists():
        return _load_workspace(config_path)

    for workspace in list_workspaces():
        if workspace.merge_branch == target_branch:
            return workspace
    return None


def list_workspaces() -> list[WorkspaceConfig]:
    workspace_dir = _workspace_dir()
    if not workspace_dir.exists():
        return []
    return [_load_workspace(path) for path in sorted(workspace_dir.glob("*.json"))]


def delete_workspace(branch_name: str) -> None:
    config_path = _workspace_config_path(branch_name)
    ref_path = _workspace_ref_path(branch_name)
    if config_path.exists():
        config_path.unlink()
    if ref_path.exists():
        ref_path.unlink()


def count_post_merge_commits(workspace: WorkspaceConfig) -> int:
    merge_commit = get_workspace_merge_commit(workspace.name)
    if merge_commit is None:
        return 0
    result = run_git(
        ["rev-list", "--count", f"{merge_commit}..{workspace.merge_branch}"]
    )
    return int(result.stdout.strip())


def recompute_workspace_merge(workspace: WorkspaceConfig, temp_branch: str) -> str:
    original_branch = get_current_branch()
    try:
        new_base = get_merge_base(workspace.branches)
        run_git(["checkout", "-B", temp_branch, new_base])
        run_git(
            [
                "merge",
                "--no-ff",
                "-m",
                f"gitcuttle workspace merge: {', '.join(workspace.branches)}",
                *workspace.branches,
            ]
        )
        return get_head_commit()
    finally:
        run_git(["checkout", original_branch])
