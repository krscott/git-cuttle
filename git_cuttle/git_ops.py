import subprocess
from pathlib import Path


BACKUP_REF_PREFIX = "refs/gitcuttle/txn"


IN_PROGRESS_STATE_MARKERS = (
    "MERGE_HEAD",
    "CHERRY_PICK_HEAD",
    "REVERT_HEAD",
    "REBASE_HEAD",
    "rebase-apply",
    "rebase-merge",
)


def in_git_repo(cwd: Path | None = None) -> bool:
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=False,
        cwd=cwd,
    )
    return result.returncode == 0


def repo_root(cwd: Path | None = None) -> Path | None:
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=False,
        cwd=cwd,
    )
    if result.returncode != 0:
        return None

    return Path(result.stdout.strip()).resolve(strict=False)


def git_dir(cwd: Path | None = None) -> Path | None:
    result = subprocess.run(
        ["git", "rev-parse", "--git-dir"],
        capture_output=True,
        text=True,
        check=False,
        cwd=cwd,
    )
    if result.returncode != 0:
        return None

    candidate = Path(result.stdout.strip())
    if candidate.is_absolute():
        return candidate

    base_dir = cwd or Path.cwd()
    return (base_dir / candidate).resolve(strict=False)


def canonical_git_dir(cwd: Path | None = None) -> Path | None:
    git_dir_path = git_dir(cwd)
    if git_dir_path is None:
        return None
    return git_dir_path.resolve(strict=False)


def default_remote_name(cwd: Path | None = None) -> str | None:
    result = subprocess.run(
        ["git", "remote"],
        capture_output=True,
        text=True,
        check=False,
        cwd=cwd,
    )
    if result.returncode != 0:
        return None

    remotes = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if not remotes:
        return None
    if "origin" in remotes:
        return "origin"
    return sorted(remotes)[0]


def in_progress_operation(cwd: Path | None = None) -> str | None:
    repo_git_dir = git_dir(cwd)
    if repo_git_dir is None:
        return None

    for marker in IN_PROGRESS_STATE_MARKERS:
        if (repo_git_dir / marker).exists():
            return marker

    return None


def backup_ref_for_branch(*, txn_id: str, branch: str) -> str:
    return f"{BACKUP_REF_PREFIX}/{txn_id}/heads/{branch}"


def create_backup_refs_for_branches(
    *,
    txn_id: str,
    branches: list[str],
    cwd: Path | None = None,
) -> dict[str, str]:
    backup_refs: dict[str, str] = {}
    for branch in branches:
        head_ref = f"refs/heads/{branch}"
        head_oid = _rev_parse_ref(head_ref=head_ref, cwd=cwd)
        if head_oid is None:
            raise RuntimeError(f"branch does not exist: {branch}")

        backup_ref = backup_ref_for_branch(txn_id=txn_id, branch=branch)
        _update_ref(ref=backup_ref, oid=head_oid, cwd=cwd)
        backup_refs[branch] = backup_ref

    return backup_refs


def restore_branch_from_backup_ref(
    *,
    txn_id: str,
    branch: str,
    cwd: Path | None = None,
) -> None:
    backup_ref = backup_ref_for_branch(txn_id=txn_id, branch=branch)
    backup_oid = _rev_parse_ref(head_ref=backup_ref, cwd=cwd)
    if backup_oid is None:
        raise RuntimeError(f"backup ref does not exist: {backup_ref}")

    _update_ref(ref=f"refs/heads/{branch}", oid=backup_oid, cwd=cwd)


def set_branch_head(*, branch: str, oid: str, cwd: Path | None = None) -> None:
    _update_ref(ref=f"refs/heads/{branch}", oid=oid, cwd=cwd)


def add_worktree(*, branch: str, path: Path, cwd: Path | None = None) -> None:
    result = subprocess.run(
        ["git", "worktree", "add", str(path), branch],
        capture_output=True,
        text=True,
        check=False,
        cwd=cwd,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"failed to add worktree {path}")


def remove_worktree(*, path: Path, cwd: Path | None = None, force: bool = False) -> None:
    command = ["git", "worktree", "remove"]
    if force:
        command.append("--force")
    command.append(str(path))

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
        cwd=cwd,
    )
    if result.returncode != 0:
        raise RuntimeError(
            result.stderr.strip() or f"failed to remove worktree {path}"
        )


def remove_backup_refs(*, txn_id: str, cwd: Path | None = None) -> None:
    prefix = f"{BACKUP_REF_PREFIX}/{txn_id}"
    refs_result = subprocess.run(
        ["git", "for-each-ref", "--format=%(refname)", prefix],
        capture_output=True,
        text=True,
        check=False,
        cwd=cwd,
    )
    if refs_result.returncode != 0:
        raise RuntimeError(refs_result.stderr.strip() or "failed to list backup refs")

    refs = [line.strip() for line in refs_result.stdout.splitlines() if line.strip()]
    for ref in refs:
        delete_result = subprocess.run(
            ["git", "update-ref", "-d", ref],
            capture_output=True,
            text=True,
            check=False,
            cwd=cwd,
        )
        if delete_result.returncode != 0:
            raise RuntimeError(
                delete_result.stderr.strip() or f"failed to delete ref {ref}"
            )


def _rev_parse_ref(*, head_ref: str, cwd: Path | None = None) -> str | None:
    result = subprocess.run(
        ["git", "rev-parse", "--verify", head_ref],
        capture_output=True,
        text=True,
        check=False,
        cwd=cwd,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def _update_ref(*, ref: str, oid: str, cwd: Path | None = None) -> None:
    result = subprocess.run(
        ["git", "update-ref", ref, oid],
        capture_output=True,
        text=True,
        check=False,
        cwd=cwd,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"failed to update ref {ref}")
