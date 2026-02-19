from __future__ import annotations

import sys

from git_cuttle.cli import main as cli_main


def main() -> None:
    raise SystemExit(cli_main(sys.argv[1:]))


if __name__ == "__main__":
    main()
