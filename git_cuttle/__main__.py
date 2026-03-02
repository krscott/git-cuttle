import logging
import sys

from dotenv import find_dotenv, load_dotenv
from setproctitle import setproctitle

from git_cuttle.cli import CliOpts, EnvAction
from git_cuttle.errors import AppError, format_user_error
from git_cuttle.orchestrator import run
from git_cuttle.transaction import TransactionRollbackError

__all__ = ["main", "EnvAction"]


def main() -> None:
    setproctitle("gitcuttle")
    load_dotenv(find_dotenv(usecwd=True))

    try:
        cli_opts = CliOpts.parse_args()

        logging.basicConfig(
            level=logging.DEBUG if cli_opts.verbose else logging.INFO,
            format="%(message)s",
        )

        run(cli_opts.app_opts, command_name=cli_opts.command_name)
    except AppError as error:
        print(
            format_user_error(error),
            file=sys.stderr,
        )
        raise SystemExit(2)
    except TransactionRollbackError as rollback_error:
        print(
            format_user_error(
                AppError(
                    code="transaction-rollback-failed",
                    message="operation failed and automatic rollback was partial",
                    details=rollback_error.format_partial_state(),
                    guidance=(
                        "run the listed recovery commands to restore repository state",
                    ),
                )
            ),
            file=sys.stderr,
        )
        raise SystemExit(2)
