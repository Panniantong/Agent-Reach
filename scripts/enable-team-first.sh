#!/usr/bin/env bash
# Enable Team-First (8 experts + Supervisor) in ~/.agent-reach/daily_run_settings.json
#
# Usage:
#   bash scripts/enable-team-first.sh
#   bash scripts/enable-team-first.sh --dry-run
#   python3 -m agent_reach.cli daily-run configure team
set -euo pipefail

DRY_RUN=""
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN="--dry-run" ;;
    -h|--help)
      echo "Usage: bash scripts/enable-team-first.sh [--dry-run]"
      echo "  or:  python3 -m agent_reach.cli daily-run configure team"
      exit 0
      ;;
    *)
      echo "Unknown option: $arg" >&2
      exit 1
      ;;
  esac
done

python3 -m agent_reach.cli daily-run configure team ${DRY_RUN:+$DRY_RUN}
