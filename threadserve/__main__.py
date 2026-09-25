"""CLI entry point for ThreadServe.

Build order note: this wires up to a real server starting in Phase 3
(threadserve.server / worker_pool / worker) and to ServerConfig starting
at Phase 3's contract-freeze step. Until then it's a placeholder.
"""

import sys


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    print("ThreadServe: server not implemented yet (see build plan, Phase 3).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
