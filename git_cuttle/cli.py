import argparse
import os
from dataclasses import dataclass
from typing import Any

from git_cuttle.lib import Options


@dataclass(kw_only=True, frozen=True)
class CliOpts:
    app_opts: Options
    verbose: bool

    @staticmethod
    def parse_args() -> "CliOpts":
        parser = argparse.ArgumentParser()

        parser.add_argument("name", nargs="?", default="World", help="Your name")
        parser.add_argument(
            "--destination",
            action="store_true",
            help="print destination path only",
        )
        parser.add_argument(
            "-v",
            "--verbose",
            action=EnvAction,
            env_var="GITCUTTLE_VERBOSE",
            nargs=0,
            help="show more detailed log messages",
        )

        args = parser.parse_args()

        return CliOpts(
            app_opts=Options(name=args.name, destination=args.destination),
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
