from __future__ import annotations

import sys

from projectpilot import __version__
from projectpilot.cli import main as projectpilot_main


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args == ["--version"] or args == ["-V"]:
        print(f"projectpilot-executor {__version__}")
        return 0
    return projectpilot_main(["executor", *args])


if __name__ == "__main__":
    raise SystemExit(main())
