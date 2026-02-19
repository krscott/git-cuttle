from __future__ import annotations

import subprocess


class GitCuttleError(Exception):
    pass


class GitCommandError(GitCuttleError):
    def __init__(self, args: list[str], stderr: str) -> None:
        command = "git " + " ".join(args)
        super().__init__(f"Command failed: {command}\n{stderr.strip()}")
        self.args_list = args
        self.stderr = stderr


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


def rebase_onto(upstream_exclusive: str, new_base: str, branch: str) -> None:
    run_git(["rebase", "--onto", new_base, upstream_exclusive, branch])


def pull_remote(branch: str, remote: str = "origin") -> None:
    run_git(["pull", "--ff-only", remote, branch])
