import logging
import sys

from dotenv import find_dotenv, load_dotenv
from setproctitle import setproctitle

from git_cuttle.cli import CliOpts, EnvAction
from git_cuttle.errors import AppError, format_user_error
from git_cuttle.orchestrator import run

__all__ = ["main", "EnvAction"]


def main() -> None:
    setproctitle("gitcuttle")
    load_dotenv(find_dotenv(usecwd=True))

    cli_opts = CliOpts.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if cli_opts.verbose else logging.INFO,
        format="%(message)s",
    )

    try:
        run(cli_opts.app_opts)
    except AppError as error:
        print(
            format_user_error(error),
            file=sys.stderr,
        )
        raise SystemExit(2)
