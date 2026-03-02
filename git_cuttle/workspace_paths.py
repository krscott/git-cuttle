import hashlib
import os
import re
from pathlib import Path
from typing import Collection


def derive_workspace_path(
    *,
    git_dir: Path,
    branch: str,
    sibling_branches: Collection[str] = (),
) -> Path:
    repo_id = derive_repo_id(git_dir)
    branch_dir = derive_branch_dir(branch)

    if _has_sanitized_collision(branch=branch, sibling_branches=sibling_branches):
        suffix = _stable_short_hash(branch, length=6)
        branch_dir = f"{branch_dir}-{suffix}"

    return _workspace_root_dir() / repo_id / branch_dir


def derive_repo_id(git_dir: Path) -> str:
    canonical_git_dir = git_dir.resolve(strict=False)
    repo_slug = _slugify_repo_name(canonical_git_dir.parent.name)
    repo_hash = hashlib.sha256(str(canonical_git_dir).encode("utf-8")).hexdigest()[:8]
    return f"{repo_slug}-{repo_hash}"


def derive_branch_dir(branch: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9._-]+", "-", branch).strip("-._").lower()
    return sanitized or "workspace"


def _workspace_root_dir() -> Path:
    data_home = os.environ.get("XDG_DATA_HOME")
    if data_home:
        return Path(data_home) / "gitcuttle"
    return Path.home() / ".local" / "share" / "gitcuttle"


def _slugify_repo_name(repo_name: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", repo_name).strip("-").lower()
    return slug or "repo"


def _has_sanitized_collision(*, branch: str, sibling_branches: Collection[str]) -> bool:
    branch_dir = derive_branch_dir(branch)
    for sibling in sibling_branches:
        if sibling == branch:
            continue
        if derive_branch_dir(sibling) == branch_dir:
            return True
    return False


def _stable_short_hash(value: str, *, length: int) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]
