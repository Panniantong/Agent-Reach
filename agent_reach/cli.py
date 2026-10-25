# -*- coding: utf-8 -*-
"""Console entry point for `agent-reach`; all commands live in agent_reach.runtime.cli."""

import os
import sys


def _ensure_utf8_console():
    """Best-effort Windows console UTF-8 setup for CLI runtime only."""
    if sys.platform != "win32":
        return
    # Avoid interfering with pytest/captured streams.
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return
    try:
        import io
        if hasattr(sys.stdout, "buffer"):
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "buffer"):
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    except Exception:
        # Do not crash CLI just because encoding patch failed.
        pass


def _configure_logging(verbose: bool = False):
    """Suppress loguru output unless --verbose is set."""
    from loguru import logger
    logger.remove()  # Remove default stderr handler
    if verbose:
        logger.add(sys.stderr, level="INFO")


def main():
    _ensure_utf8_console()
    argv = sys.argv[1:]
    # Arguments after -- are literal values, including verbosity-looking queries.
    options_end = argv.index("--") if "--" in argv else len(argv)
    options = argv[:options_end]
    verbose = any(a in ("-v", "--verbose") for a in options)
    argv = [a for a in options if a not in ("-v", "--verbose")] + argv[options_end:]
    _configure_logging(verbose)

    from agent_reach.runtime import cli as unified

    sys.exit(unified.main(argv))


if __name__ == "__main__":
    main()
