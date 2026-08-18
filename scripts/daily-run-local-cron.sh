#!/usr/bin/env bash
# Run one daily-run scheduled job locally (for Linux/macOS user crontab).
#
# Install all slots:
#   python3 -m agent_reach.cli daily-run schedule install
#
# Manual:
#   ./scripts/daily-run-local-cron.sh morning
#
set -euo pipefail

JOB="${1:-}"
if [ -z "$JOB" ]; then
  echo "usage: daily-run-local-cron.sh morning|intraday|close|weekly|forecast" >&2
  exit 2
fi
case "$JOB" in
  morning|intraday|close|weekly|forecast) ;;
  *)
    echo "unknown job: $JOB" >&2
    exit 2
    ;;
esac

export TZ="${TZ:-Asia/Shanghai}"
# Cron redirects stdout to a file; unbuffered so progress appears in cron-YYYY-MM-DD.log
export PYTHONUNBUFFERED=1

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PYTHON="${DAILY_RUN_PYTHON:-}"
if [ -z "$PYTHON" ] && [ -x "${REPO_ROOT}/venv/bin/python3" ]; then
  PYTHON="${REPO_ROOT}/venv/bin/python3"
else
  PYTHON="${PYTHON:-python3}"
fi
export PATH="${HOME}/.local/node/bin:${PATH}"
LOG_DIR="${HOME}/.agent-reach/daily_run/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="${LOG_DIR}/cron-$(date +%Y-%m-%d).log"

export MCPORTER_CONFIG="${MCPORTER_CONFIG:-${REPO_ROOT}/config/mcporter.json}"

# Load local secrets (Feishu, RedFox, etc.) — never commit this file
ENV_FILE="${HOME}/.agent-reach/config.env"
if [ -f "$ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

if [ ! -f "${HOME}/.agent-reach/config.yaml" ]; then
  {
    echo "=== $(date -Iseconds) job=${JOB} ERROR ==="
    echo "missing ~/.agent-reach/config.yaml — run: python3 -m agent_reach.cli setup"
  } >>"$LOG_FILE"
  exit 1
fi

{
  echo "=== $(date -Iseconds) job=${JOB} pid=$$ ==="
} >>"$LOG_FILE"

cd "$REPO_ROOT"
set +e
"$PYTHON" -m agent_reach.cli daily-run schedule run "$JOB" >>"$LOG_FILE" 2>&1
ec=$?
set -e
{
  echo "=== exit=${ec} ==="
} >>"$LOG_FILE"
exit "$ec"
