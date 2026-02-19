from __future__ import annotations

import argparse
import logging

from git_cuttle.git_ops import GitCuttleError, get_current_branch
from git_cuttle.rebase import rebase_workspace_commits, update_workspace
from git_cuttle.workspace import (
    count_post_merge_commits,
    create_workspace,
    get_workspace,
    list_workspaces,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gitcuttle")
    parser.add_argument("-v", "--verbose", action="store_true", help="verbose logging")
    subparsers = parser.add_subparsers(dest="command", required=True)

    new_parser = subparsers.add_parser("new", help="create a new workspace")
    new_parser.add_argument("branches", nargs="+", help="branches to merge")
    new_parser.add_argument("--name", help="workspace branch name")

    absorb_parser = subparsers.add_parser(
        "absorb", help="rebase workspace commits onto refreshed merge"
    )
    absorb_parser.add_argument(
        "--continue", dest="continue_rebase", action="store_true"
    )

    update_parser = subparsers.add_parser(
        "update", help="pull parent branches then rebase workspace"
    )
    update_parser.add_argument(
        "--continue", dest="continue_rebase", action="store_true"
    )

    subparsers.add_parser("list", help="list workspaces")
    subparsers.add_parser("status", help="show current workspace status")
    return parser


def _show_workspace_status() -> int:
    current = get_current_branch()
    workspace = get_workspace(current)
    if workspace is None:
        print(f"{current}: not a tracked gitcuttle workspace")
        return 1

    post_merge_count = count_post_merge_commits(workspace)
    branches = ", ".join(workspace.branches)
    print(f"workspace: {workspace.name}")
    print(f"parents: {branches}")
    print(f"post-merge commits: {post_merge_count}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO, format="%(message)s"
    )

    try:
        if args.command == "new":
            if len(args.branches) < 2:
                raise GitCuttleError("new requires at least two branches")
            created_workspace = create_workspace(args.branches, args.name)
            print(f"created workspace: {created_workspace.name}")
            return 0

        elif args.command == "absorb":
            current_workspace = get_workspace()
            if current_workspace is None:
                raise GitCuttleError("current branch is not a gitcuttle workspace")
            rebase_workspace_commits(
                current_workspace,
                operation="rebase",
                continue_rebase=args.continue_rebase,
            )
            print(f"workspace rebased: {current_workspace.name}")
            return 0

        elif args.command == "update":
            current_workspace = get_workspace()
            if current_workspace is None:
                raise GitCuttleError("current branch is not a gitcuttle workspace")
            update_workspace(current_workspace, continue_rebase=args.continue_rebase)
            print(f"workspace updated: {current_workspace.name}")
            return 0

        elif args.command == "list":
            workspaces = list_workspaces()
            if not workspaces:
                print("no workspaces")
                return 0
            for workspace in workspaces:
                print(f"{workspace.name}: {', '.join(workspace.branches)}")
            return 0

        elif args.command == "status":
            return _show_workspace_status()

        parser.error("unknown command")
        return 2
    except GitCuttleError as exc:
        print(str(exc))
        return 1
