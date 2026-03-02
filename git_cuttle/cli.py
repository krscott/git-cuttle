from __future__ import annotations

import argparse
import logging
import sys

from git_cuttle.git_ops import (
    GitCuttleError,
    branch_exists_local,
    get_current_branch,
    get_head_commit,
    run_git,
)
from git_cuttle.rebase import rebase_workspace_commits, update_workspace
from git_cuttle.workspace import (
    WorkspaceConfig,
    count_post_merge_commits,
    create_workspace,
    delete_workspace,
    generate_workspace_name,
    get_workspace,
    list_workspaces,
)
from git_cuttle.worktree_tracking import (
    TrackedWorktree,
    delete_tracked_worktree,
    ensure_branch_worktree,
    ensure_workspace_worktree,
    get_tracked_worktree,
    list_tracked_worktrees,
    precheck_worktree_target,
    remove_tracked_worktree_path,
    save_tracked_worktree,
    tracked_worktree_metadata_path,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gitcuttle")
    parser.add_argument("-v", "--verbose", action="store_true", help="verbose logging")
    subparsers = parser.add_subparsers(dest="command", required=True)

    new_parser = subparsers.add_parser("new", help="create a new workspace")
    new_parser.add_argument("branches", nargs="+", help="branches to merge")
    new_parser.add_argument("--name", help="workspace branch name")

    worktree_parser = subparsers.add_parser(
        "worktree", help="create tracked worktree for branch or workspace"
    )
    worktree_parser.add_argument("branches", nargs="+", help="branch or branches")
    worktree_parser.add_argument("--name", help="workspace branch name")
    worktree_parser.add_argument(
        "--print-path",
        action="store_true",
        help="print only resulting worktree path",
    )

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

    delete_parser = subparsers.add_parser(
        "delete", help="delete tracked workspace/worktree"
    )
    delete_target_group = delete_parser.add_mutually_exclusive_group()
    delete_target_group.add_argument(
        "--workspace-only",
        action="store_true",
        help="delete only workspace metadata",
    )
    delete_target_group.add_argument(
        "--worktree-only",
        action="store_true",
        help="delete only tracked worktree",
    )
    delete_parser.add_argument(
        "workspace",
        nargs="?",
        help="workspace or branch name (defaults to current branch)",
    )

    subparsers.add_parser("list", help="list workspaces and tracked worktrees")
    subparsers.add_parser("status", help="show current tracked status")
    return parser


def _show_status() -> int:
    current = get_current_branch()
    workspace = get_workspace(current)
    tracked_worktree = get_tracked_worktree(current)

    if workspace is None and tracked_worktree is None:
        print(f"{current}: not tracked by gitcuttle")
        return 1

    if workspace is not None:
        post_merge_count = count_post_merge_commits(workspace)
        branches = ", ".join(workspace.branches)
        print(f"workspace: {workspace.name}")
        print(f"parents: {branches}")
        print(f"post-merge commits: {post_merge_count}")
        if tracked_worktree is not None and _is_workspace_tracked_worktree_pair(
            workspace=workspace,
            tracked_worktree=tracked_worktree,
        ):
            print(f"worktree path: {tracked_worktree.path}")
        return 0

    assert tracked_worktree is not None
    print(f"branch: {tracked_worktree.branch}")
    print("type: tracked worktree")
    print(f"worktree path: {tracked_worktree.path}")
    return 0


def _show_worktree_result(
    path: str,
    print_path: bool,
    reused: bool,
    workspace_name: str | None,
) -> None:
    if print_path:
        print(path)
        return

    if workspace_name is not None:
        print(f"created workspace: {workspace_name}")
    action = "reused" if reused else "created"
    print(f"{action} worktree: {path}")
    print(f"cd {path}")


def _show_list() -> int:
    workspaces = list_workspaces()
    tracked_worktrees = list_tracked_worktrees()

    if not workspaces and not tracked_worktrees:
        print("no tracked workspaces or worktrees")
        return 0

    workspace_by_merge_branch = {
        workspace.merge_branch: workspace for workspace in workspaces
    }
    linked_workspace_path_by_name: dict[str, str] = {}
    unlinked_tracked_lines: list[str] = []

    for tracked in tracked_worktrees:
        if tracked.kind == "workspace":
            matching_workspace = workspace_by_merge_branch.get(tracked.branch)
            if matching_workspace is not None and _is_workspace_tracked_worktree_pair(
                workspace=matching_workspace,
                tracked_worktree=tracked,
            ):
                linked_workspace_path_by_name[matching_workspace.name] = tracked.path
                continue

            workspace_name = tracked.workspace_name or tracked.branch
            unlinked_tracked_lines.append(
                f"{tracked.branch} [orphan-workspace-worktree]: "
                f"workspace={workspace_name} path={tracked.path}"
            )
            continue

        unlinked_tracked_lines.append(f"{tracked.branch} [branch]: path={tracked.path}")

    for workspace in workspaces:
        branches = ", ".join(workspace.branches)
        linked_path = linked_workspace_path_by_name.get(workspace.name)
        if linked_path is None:
            print(f"{workspace.name} [workspace]: parents={branches}")
        else:
            print(
                f"{workspace.name} [workspace]: parents={branches} path={linked_path}"
            )

    for line in unlinked_tracked_lines:
        print(line)

    return 0


def _rollback_workspace_creation(
    workspace_name: str, original_branch: str, original_head: str
) -> str | None:
    errors: list[str] = []

    if get_current_branch() == workspace_name:
        try:
            _restore_original_checkout(original_branch, original_head)
        except GitCuttleError as exc:
            errors.append(f"failed to restore original branch: {exc}")

    try:
        delete_workspace(workspace_name)
    except OSError as exc:
        errors.append(f"failed to remove workspace metadata: {exc}")

    if branch_exists_local(workspace_name):
        try:
            run_git(["branch", "-D", workspace_name])
        except GitCuttleError as exc:
            errors.append(f"failed to delete workspace branch: {exc}")

    if not errors:
        return None

    return "; ".join(errors)


def _restore_original_checkout(original_branch: str, original_head: str) -> None:
    if original_branch:
        run_git(["checkout", original_branch])
        return
    run_git(["checkout", "--detach", original_head])


def _format_workspace_creation_error(
    exc: Exception, workspace_name: str, rollback_error: str | None
) -> str:
    if rollback_error is None:
        return f"{exc}\nrolled back created workspace: {workspace_name}"
    return (
        f"{exc}\nrollback incomplete for workspace {workspace_name}: {rollback_error}"
    )


def _is_workspace_tracked_worktree_pair(
    workspace: WorkspaceConfig, tracked_worktree: TrackedWorktree
) -> bool:
    return (
        tracked_worktree.branch == workspace.merge_branch
        and tracked_worktree.kind == "workspace"
        and tracked_worktree.workspace_name == workspace.name
    )


def _delete_tracked_worktree_entry(
    target_name: str, tracked_worktree: TrackedWorktree
) -> None:
    if tracked_worktree.branch != target_name:
        raise GitCuttleError(
            "tracked worktree metadata mismatch: "
            f"requested {target_name}, but metadata points to {tracked_worktree.branch}"
        )

    metadata_path = tracked_worktree_metadata_path(target_name)
    remove_tracked_worktree_path(tracked_worktree)
    delete_tracked_worktree(target_name, metadata_path=metadata_path)


def _convert_to_branch_worktree(tracked_worktree: TrackedWorktree) -> TrackedWorktree:
    return TrackedWorktree(
        branch=tracked_worktree.branch,
        path=tracked_worktree.path,
        kind="branch",
        workspace_name=None,
    )


def _delete_target(
    target_name: str,
    target_workspace: WorkspaceConfig | None,
    tracked_worktree: TrackedWorktree | None,
    *,
    workspace_only: bool,
    worktree_only: bool,
) -> str:
    if target_workspace is None and tracked_worktree is None:
        raise GitCuttleError("workspace or tracked worktree not found")

    if workspace_only:
        if target_workspace is None:
            raise GitCuttleError("workspace not found")
        delete_workspace(target_workspace.name)
        if tracked_worktree is not None and _is_workspace_tracked_worktree_pair(
            workspace=target_workspace,
            tracked_worktree=tracked_worktree,
        ):
            save_tracked_worktree(_convert_to_branch_worktree(tracked_worktree))
        return f"deleted workspace metadata: {target_workspace.name}"

    if worktree_only:
        if tracked_worktree is None:
            raise GitCuttleError("tracked worktree not found")
        _delete_tracked_worktree_entry(target_name, tracked_worktree)
        return f"deleted tracked worktree: {target_name}"

    if (
        target_workspace is not None
        and tracked_worktree is not None
        and not _is_workspace_tracked_worktree_pair(
            workspace=target_workspace,
            tracked_worktree=tracked_worktree,
        )
    ):
        raise GitCuttleError(
            f"ambiguous delete target: {target_name}. "
            "use --workspace-only or --worktree-only"
        )

    if tracked_worktree is not None:
        _delete_tracked_worktree_entry(target_name, tracked_worktree)

    if target_workspace is not None:
        delete_workspace(target_workspace.name)

    if target_workspace is not None and tracked_worktree is not None:
        return f"deleted workspace and worktree: {target_workspace.name}"
    if target_workspace is not None:
        return f"deleted workspace metadata: {target_workspace.name}"
    if tracked_worktree is not None:
        return f"deleted tracked worktree: {target_name}"

    raise GitCuttleError("workspace or tracked worktree not found")


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

        elif args.command == "worktree":
            if len(args.branches) == 1:
                if args.name is not None:
                    raise GitCuttleError("--name is only valid for multiple branches")
                result = ensure_branch_worktree(args.branches[0])
                _show_worktree_result(
                    path=result.tracked.path,
                    print_path=args.print_path,
                    reused=result.reused,
                    workspace_name=None,
                )
                return 0

            workspace_name = args.name or generate_workspace_name(args.branches)
            precheck_worktree_target(workspace_name)

            original_branch = get_current_branch()
            original_head = get_head_commit()
            created_workspace = create_workspace(args.branches, workspace_name)
            try:
                if get_current_branch() == created_workspace.merge_branch:
                    _restore_original_checkout(original_branch, original_head)
                result = ensure_workspace_worktree(created_workspace)
            except Exception as exc:
                rollback_error = _rollback_workspace_creation(
                    created_workspace.name,
                    original_branch,
                    original_head,
                )
                raise GitCuttleError(
                    _format_workspace_creation_error(
                        exc, created_workspace.name, rollback_error
                    )
                ) from exc

            _show_worktree_result(
                path=result.tracked.path,
                print_path=args.print_path,
                reused=result.reused,
                workspace_name=created_workspace.name,
            )
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

        elif args.command == "delete":
            target_name = args.workspace or get_current_branch()
            target_workspace = get_workspace(target_name)
            tracked_worktree = get_tracked_worktree(target_name)
            result_message = _delete_target(
                target_name=target_name,
                target_workspace=target_workspace,
                tracked_worktree=tracked_worktree,
                workspace_only=args.workspace_only,
                worktree_only=args.worktree_only,
            )

            print(result_message)
            return 0

        elif args.command == "list":
            return _show_list()

        elif args.command == "status":
            return _show_status()

        parser.error("unknown command")
        return 2
    except GitCuttleError as exc:
        print(str(exc), file=sys.stderr)
        return 1
