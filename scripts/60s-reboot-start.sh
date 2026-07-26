#!/usr/bin/env bash
# Start local 60s API + web portal after system reboot (invoked by user crontab @reboot).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PYTHON="${AGENT_REACH_PYTHON:-}"
if [ -z "$PYTHON" ] && [ -x "${REPO_ROOT}/venv/bin/python3" ]; then
  PYTHON="${REPO_ROOT}/venv/bin/python3"
else
  PYTHON="${PYTHON:-python3}"
fi

export PATH="${HOME}/.local/node/bin:${PATH}"

LOG_DIR="${HOME}/.agent-reach/daily_run/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="${LOG_DIR}/60s-reboot-$(date +%Y-%m-%d).log"

{
  echo "=== $(date -Iseconds) pid=$$ reboot start ==="
  "$PYTHON" -m agent_reach.cli daily-run hot-news install --mode native --no-reboot-cron
  echo "=== exit=$? ==="
} >>"$LOG_FILE" 2>&1
