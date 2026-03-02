from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


class GitCuttleError(Exception):
    pass


class GitCommandError(GitCuttleError):
    def __init__(self, args: list[str], stderr: str) -> None:
        command = "git " + " ".join(args)
        super().__init__(f"Command failed: {command}\n{stderr.strip()}")
        self.args_list = args
        self.stderr = stderr


@dataclass(frozen=True)
class GitWorktree:
    path: Path
    branch: str | None


def run_git(args: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", *args],
        check=False,
        capture_output=True,
        text=True,
    )
    if check and result.returncode != 0:
        raise GitCommandError(args, result.stderr)
    return result


def get_current_branch() -> str:
    return run_git(["branch", "--show-current"]).stdout.strip()


def get_repo_root() -> Path:
    return Path(run_git(["rev-parse", "--show-toplevel"]).stdout.strip())


def get_head_commit(ref: str = "HEAD") -> str:
    return run_git(["rev-parse", ref]).stdout.strip()


def get_merge_base(branches: list[str]) -> str:
    if len(branches) < 2:
        raise GitCuttleError("at least two branches are required")
    base = run_git(["merge-base", branches[0], branches[1]]).stdout.strip()
    for branch in branches[2:]:
        base = run_git(["merge-base", base, branch]).stdout.strip()
    return base


def is_ancestor(ancestor: str, descendant: str) -> bool:
    result = run_git(["merge-base", "--is-ancestor", ancestor, descendant], check=False)
    if result.returncode == 0:
        return True
    if result.returncode == 1:
        return False
    raise GitCommandError(
        ["merge-base", "--is-ancestor", ancestor, descendant], result.stderr
    )


def create_octopus_merge(branches: list[str], target_branch: str) -> str:
    if len(branches) < 2:
        raise GitCuttleError("at least two branches are required")
    run_git(["checkout", "-b", target_branch])
    run_git(
        [
            "merge",
            "--no-ff",
            "-m",
            f"gitcuttle workspace merge: {', '.join(branches)}",
            *branches,
        ]
    )
    return get_head_commit()


def branch_exists_local(branch: str) -> bool:
    result = run_git(
        ["show-ref", "--verify", "--quiet", f"refs/heads/{branch}"], check=False
    )
    return result.returncode == 0


def list_remote_branch_matches(branch: str) -> list[str]:
    result = run_git(["for-each-ref", "--format=%(refname:short)", "refs/remotes"])
    matches: list[str] = []
    for line in result.stdout.splitlines():
        ref_name = line.strip()
        if not ref_name or ref_name.endswith("/HEAD"):
            continue
        _, separator, branch_name = ref_name.partition("/")
        if separator and branch_name == branch:
            matches.append(ref_name)
    return sorted(matches)


def list_git_worktrees() -> list[GitWorktree]:
    result = run_git(["worktree", "list", "--porcelain"])
    lines = result.stdout.splitlines()
    worktrees: list[GitWorktree] = []
    current_path: Path | None = None
    current_branch: str | None = None

    for raw_line in [*lines, ""]:
        line = raw_line.strip()
        if line == "":
            if current_path is not None:
                worktrees.append(GitWorktree(path=current_path, branch=current_branch))
            current_path = None
            current_branch = None
            continue

        if line.startswith("worktree "):
            current_path = Path(line.removeprefix("worktree "))
        elif line.startswith("branch "):
            branch_ref = line.removeprefix("branch ")
            current_branch = branch_ref.removeprefix("refs/heads/")

    return worktrees


def add_git_worktree(path: Path, branch: str) -> None:
    run_git(["worktree", "add", str(path), branch])


def add_git_worktree_from_remote(path: Path, branch: str, remote_ref: str) -> None:
    run_git(["worktree", "add", "--track", "-b", branch, str(path), remote_ref])


def remove_git_worktree(path: Path) -> None:
    run_git(["worktree", "remove", str(path)])


def rebase_onto(upstream_exclusive: str, new_base: str, branch: str) -> None:
    run_git(["rebase", "--onto", new_base, upstream_exclusive, branch])


def pull_remote(branch: str, remote: str = "origin") -> None:
    run_git(["pull", "--ff-only", remote, branch])
