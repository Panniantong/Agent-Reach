"""Run a subprocess after loading the Agent Reach local .env file."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from agent_reach.envfile import DEFAULT_ENV_FILE, load_agent_env


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a command with Agent Reach .env loaded")
    parser.add_argument("--env-file", default=str(DEFAULT_ENV_FILE))
    parser.add_argument("command")
    parser.add_argument("args", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)

    load_agent_env(Path(args.env_file), override=True)
    return subprocess.call([args.command, *args.args])


if __name__ == "__main__":
    raise SystemExit(main())
