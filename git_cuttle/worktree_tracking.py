from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass
from json import JSONDecodeError
from pathlib import Path
from typing import Literal, cast

from git_cuttle.git_ops import (
    GitCuttleError,
    add_git_worktree,
    add_git_worktree_from_remote,
    branch_exists_local,
    get_current_branch,
    get_repo_root,
    list_git_worktrees,
    list_remote_branch_matches,
    remove_git_worktree,
    run_git,
)
from git_cuttle.workspace import WorkspaceConfig

TrackedWorktreeKind = Literal["branch", "workspace"]


@dataclass(frozen=True)
class TrackedWorktree:
    branch: str
    path: str
    kind: TrackedWorktreeKind
    workspace_name: str | None


@dataclass(frozen=True)
class EnsureWorktreeResult:
    tracked: TrackedWorktree
    reused: bool


def _git_dir() -> Path:
    return Path(run_git(["rev-parse", "--git-common-dir"]).stdout.strip())


def _tracked_worktree_dir() -> Path:
    return _git_dir() / "gitcuttle" / "tracked-worktrees"


def _branch_key(branch: str) -> str:
    return hashlib.sha256(branch.encode("utf-8")).hexdigest()


def _tracked_worktree_path(branch: str) -> Path:
    return _tracked_worktree_dir() / f"{_branch_key(branch)}.json"


def _load_tracked_worktree(path: Path) -> TrackedWorktree:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (JSONDecodeError, OSError) as exc:
        raise GitCuttleError(
            f"invalid tracked worktree metadata file: {path}: {exc}"
        ) from exc

    if not isinstance(payload, dict):
        raise GitCuttleError(
            f"invalid tracked worktree metadata file: {path}: expected object"
        )
    payload_dict = cast(dict[str, object], payload)

    branch_raw = payload_dict.get("branch")
    path_raw = payload_dict.get("path")
    kind_raw = payload_dict.get("kind")
    workspace_name = payload_dict.get("workspace_name")

    if not isinstance(branch_raw, str) or not branch_raw:
        raise GitCuttleError(
            f"invalid tracked worktree metadata file: {path}: invalid branch"
        )
    if not isinstance(path_raw, str) or not path_raw:
        raise GitCuttleError(
            f"invalid tracked worktree metadata file: {path}: invalid path"
        )
    if not isinstance(kind_raw, str) or kind_raw not in {"branch", "workspace"}:
        raise GitCuttleError(
            f"invalid tracked worktree metadata file: {path}: invalid kind"
        )
    if workspace_name is not None and not isinstance(workspace_name, str):
        raise GitCuttleError(
            f"invalid tracked worktree metadata file: {path}: invalid workspace_name"
        )

    return TrackedWorktree(
        branch=branch_raw,
        path=path_raw,
        kind=cast(TrackedWorktreeKind, kind_raw),
        workspace_name=workspace_name,
    )


def save_tracked_worktree(entry: TrackedWorktree) -> None:
    path = _tracked_worktree_path(entry.branch)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(entry), indent=2), encoding="utf-8")


def get_tracked_worktree(branch_name: str | None = None) -> TrackedWorktree | None:
    branch = branch_name or get_current_branch()
    path = _tracked_worktree_path(branch)
    if not path.exists():
        return None
    return _load_tracked_worktree(path)


def list_tracked_worktrees() -> list[TrackedWorktree]:
    tracked_dir = _tracked_worktree_dir()
    if not tracked_dir.exists():
        return []
    entries = [
        _load_tracked_worktree(path) for path in sorted(tracked_dir.glob("*.json"))
    ]
    return sorted(entries, key=lambda entry: entry.branch)


def delete_tracked_worktree(branch: str, metadata_path: Path | None = None) -> None:
    path = metadata_path or _tracked_worktree_path(branch)
    if path.exists():
        path.unlink()


def tracked_worktree_metadata_path(branch: str) -> Path:
    return _tracked_worktree_path(branch)


def _xdg_data_home() -> Path:
    xdg_data_home = os.environ.get("XDG_DATA_HOME")
    if xdg_data_home:
        return Path(xdg_data_home).expanduser().resolve()
    return (Path.home() / ".local" / "share").resolve()


def _branch_relative_path(branch: str) -> Path:
    parts = branch.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise GitCuttleError(f"invalid branch name for worktree path: {branch}")
    return Path(*parts)


def managed_worktree_path(branch: str) -> Path:
    repo_root = get_repo_root().resolve()
    repo_name = repo_root.name
    repo_fingerprint = hashlib.sha256(str(repo_root).encode("utf-8")).hexdigest()[:12]
    return (
        _xdg_data_home()
        / "gitcuttle"
        / "worktrees"
        / repo_name
        / repo_fingerprint
        / _branch_relative_path(branch)
    )


def _paths_equal(left: Path, right: Path) -> bool:
    return left.resolve() == right.resolve()


def _is_path_branch_worktree(path: Path, branch: str) -> bool:
    for worktree in list_git_worktrees():
        if _paths_equal(worktree.path, path) and worktree.branch == branch:
            return True
    return False


def _path_is_registered_worktree(path: Path) -> bool:
    for worktree in list_git_worktrees():
        if _paths_equal(worktree.path, path):
            return True
    return False


def resolve_remote_branch(branch: str) -> str:
    matches = list_remote_branch_matches(branch)
    if not matches:
        raise GitCuttleError(f"branch not found locally or on any remote: {branch}")

    preferred = f"origin/{branch}"
    if preferred in matches:
        return preferred

    if len(matches) == 1:
        return matches[0]

    joined = ", ".join(matches)
    raise GitCuttleError(f"ambiguous remote branch for {branch}: {joined}")


def _build_tracked_worktree(
    branch: str,
    kind: TrackedWorktreeKind,
    workspace_name: str | None,
) -> TrackedWorktree:
    return TrackedWorktree(
        branch=branch,
        path=str(managed_worktree_path(branch)),
        kind=kind,
        workspace_name=workspace_name,
    )


def _check_target_path(branch: str) -> tuple[Path, bool]:
    target_path = managed_worktree_path(branch)

    if target_path.exists():
        if _is_path_branch_worktree(target_path, branch):
            return target_path, True
        raise GitCuttleError(f"target worktree path already exists: {target_path}")

    if _path_is_registered_worktree(target_path):
        raise GitCuttleError(
            f"target path is already registered as a different worktree: {target_path}"
        )

    return target_path, False


def precheck_worktree_target(branch: str) -> None:
    _check_target_path(branch)


def _ensure_worktree(
    branch: str,
    kind: TrackedWorktreeKind,
    workspace_name: str | None,
) -> EnsureWorktreeResult:
    target_path, reused = _check_target_path(branch)
    if reused:
        tracked = _build_tracked_worktree(branch, kind, workspace_name)
        try:
            save_tracked_worktree(tracked)
        except OSError as exc:
            raise GitCuttleError(
                f"failed to persist tracked worktree metadata for {branch}: {exc}"
            ) from exc
        return EnsureWorktreeResult(tracked=tracked, reused=True)

    remote_ref: str | None = None
    if branch_exists_local(branch):
        if get_current_branch() == branch:
            raise GitCuttleError(
                f"branch is checked out in current worktree: {branch}. "
                "switch to another branch first"
            )
    else:
        remote_ref = resolve_remote_branch(branch)

    try:
        target_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise GitCuttleError(
            f"failed to create managed worktree directory {target_path.parent}: {exc}"
        ) from exc

    if remote_ref is None:
        add_git_worktree(target_path, branch)
    else:
        add_git_worktree_from_remote(target_path, branch, remote_ref)

    tracked = _build_tracked_worktree(branch, kind, workspace_name)
    try:
        save_tracked_worktree(tracked)
    except OSError as exc:
        raise GitCuttleError(
            f"failed to persist tracked worktree metadata for {branch}: {exc}"
        ) from exc
    return EnsureWorktreeResult(tracked=tracked, reused=False)


def ensure_branch_worktree(branch: str) -> EnsureWorktreeResult:
    return _ensure_worktree(branch=branch, kind="branch", workspace_name=None)


def ensure_workspace_worktree(workspace: WorkspaceConfig) -> EnsureWorktreeResult:
    return _ensure_worktree(
        branch=workspace.merge_branch,
        kind="workspace",
        workspace_name=workspace.name,
    )


def remove_tracked_worktree_path(entry: TrackedWorktree) -> None:
    path = Path(entry.path)
    if not path.exists():
        return

    registered_branch: str | None = None
    for worktree in list_git_worktrees():
        if _paths_equal(worktree.path, path):
            registered_branch = worktree.branch
            break

    if registered_branch is None:
        raise GitCuttleError(f"managed path exists but is not a git worktree: {path}")
    if registered_branch != entry.branch:
        raise GitCuttleError(
            "tracked worktree metadata mismatch: "
            f"branch {entry.branch} points to {path}, but path is checked out as "
            f"{registered_branch}"
        )
    remove_git_worktree(path)
