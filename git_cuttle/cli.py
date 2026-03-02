import argparse
import os
from dataclasses import dataclass
from typing import Any, NoReturn

from git_cuttle.errors import AppError
from git_cuttle.lib import Options


class ErrorHandlingArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise AppError(
            code="invalid-arguments",
            message="invalid command arguments",
            details=message,
            guidance=("run `gitcuttle --help` to view valid usage",),
        )


def add_destination_flag(parser: argparse.ArgumentParser) -> None:
    """Add shared destination output flag for navigation-style commands."""
    parser.add_argument(
        "-d",
        "--destination",
        action="store_true",
        help="print destination path only",
    )


@dataclass(kw_only=True, frozen=True)
class CliOpts:
    app_opts: Options
    command_name: str
    verbose: bool

    @staticmethod
    def parse_args() -> "CliOpts":
        parser = ErrorHandlingArgumentParser()
        parser.add_argument(
            "-v",
            "--verbose",
            action=EnvAction,
            env_var="GITCUTTLE_VERBOSE",
            nargs=0,
            help="show more detailed log messages",
        )

        subparsers = parser.add_subparsers(dest="command", required=True)

        new_parser = subparsers.add_parser("new", help="create a new workspace")
        new_parser.add_argument(
            "-b",
            "--branch",
            required=True,
            help="new branch name to create",
        )
        new_parser.add_argument(
            "bases",
            nargs="*",
            help="base ref(s): one for standard, two or more for octopus",
        )
        add_destination_flag(new_parser)

        list_parser = subparsers.add_parser("list", help="list tracked workspaces")
        list_parser.add_argument(
            "--json",
            dest="json_output",
            action="store_true",
            help="render output as json",
        )

        delete_parser = subparsers.add_parser(
            "delete", help="delete a tracked workspace"
        )
        delete_parser.add_argument("branch", help="workspace branch to delete")
        delete_parser.add_argument(
            "--dry-run", action="store_true", help="print plan without mutating"
        )
        delete_parser.add_argument(
            "--json",
            dest="json_output",
            action="store_true",
            help="render output as json",
        )
        delete_parser.add_argument(
            "--force", action="store_true", help="bypass safety checks"
        )

        prune_parser = subparsers.add_parser(
            "prune", help="prune stale tracked workspaces"
        )
        prune_parser.add_argument(
            "--dry-run", action="store_true", help="print plan without mutating"
        )
        prune_parser.add_argument(
            "--json",
            dest="json_output",
            action="store_true",
            help="render output as json",
        )
        prune_parser.add_argument(
            "--force", action="store_true", help="bypass safety checks"
        )

        subparsers.add_parser("update", help="update current workspace")

        absorb_parser = subparsers.add_parser(
            "absorb", help="absorb octopus commits into parent branches"
        )
        absorb_parser.add_argument(
            "target_parent", nargs="?", default=None, help="target parent branch"
        )
        absorb_parser.add_argument(
            "-i",
            "--interactive",
            action="store_true",
            help="choose a target parent for each commit",
        )

        args = parser.parse_args()

        base_ref: str | None = None
        parent_refs: tuple[str, ...] = ()
        if args.command == "new":
            bases: list[str] = args.bases
            if len(bases) == 1:
                base_ref = bases[0]
            elif len(bases) >= 2:
                parent_refs = tuple(bases)

        return CliOpts(
            app_opts=Options(
                branch=getattr(args, "branch", None),
                base_ref=base_ref,
                parent_refs=parent_refs,
                destination=getattr(args, "destination", False),
                dry_run=getattr(args, "dry_run", False),
                json_output=getattr(args, "json_output", False),
                force=getattr(args, "force", False),
                interactive=getattr(args, "interactive", False),
                target_parent=getattr(args, "target_parent", None),
            ),
            command_name=args.command,
            verbose=args.verbose is not None,
        )


class EnvAction(argparse.Action):
    """ArgumentParser Action for options with an env var fallback"""

    def __init__(
        self,
        help: str,
        env_var: str = "",
        required: bool = True,
        default: Any = None,
        nargs: str | int | None = None,
        **kwargs: Any,
    ) -> None:
        if default is not None and env_var:
            help += f" (default: {default}, env: {env_var})"
        elif default is not None:
            help += f" (default: {default})"
        elif env_var:
            help += f" (env: {env_var})"

        if env_var and env_var in os.environ:
            default = os.environ[env_var]
            if default == "":
                default = None

        if default is not None or nargs == 0:
            required = False

        super(EnvAction, self).__init__(
            help=help,
            default=default,
            required=required,
            nargs=nargs,
            **kwargs,
        )

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: Any,
        option_string: str | None = None,
    ) -> None:
        _ = parser
        _ = option_string
        if self.nargs == 0:
            setattr(namespace, self.dest, True)
        else:
            setattr(namespace, self.dest, values)
