#!/usr/bin/env bash
# Scheduled power-off with RTC wake for the next trading/session window.
# Boot times (06:40 / 08:40 / 12:40) are set via rtcwake when shutting down.
#
# Slots (Asia/Shanghai):
#   lunch        Mon–Fri 11:40 off → wake 12:40 same day
#   weekday_pm   Mon–Fri 16:00 off → wake next 06:40 (Sat 08:40 after Fri)
#   weekend_noon Sat/Sun 12:00 off → wake Sun 08:40 or Mon 06:40
#
# Requires: sudo bash scripts/install-power-schedule-sudo.sh (once)
set -euo pipefail

export TZ="${TZ:-Asia/Shanghai}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="${HOME}/.agent-reach/daily_run/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="${LOG_DIR}/power-schedule-$(date +%Y-%m-%d).log"

log() {
  echo "$(date '+%Y-%m-%d %H:%M:%S') $*" | tee -a "$LOG_FILE"
}

usage() {
  echo "usage: $(basename "$0") lunch|weekday_pm|weekend_noon" >&2
  exit 2
}

SLOT="${1:-}"
case "$SLOT" in
  lunch)
    WAKE="$(date -d 'today 12:40' '+%Y-%m-%d %H:%M:%S')"
    ;;
  weekday_pm)
    DOW="$(date +%u)"
    if [ "$DOW" = 5 ]; then
      WAKE="$(date -d 'next saturday 08:40' '+%Y-%m-%d %H:%M:%S')"
    else
      WAKE="$(date -d 'tomorrow 06:40' '+%Y-%m-%d %H:%M:%S')"
    fi
    ;;
  weekend_noon)
    DOW="$(date +%u)"
    if [ "$DOW" = 6 ]; then
      WAKE="$(date -d 'tomorrow 08:40' '+%Y-%m-%d %H:%M:%S')"
    elif [ "$DOW" = 7 ]; then
      WAKE="$(date -d 'next monday 06:40' '+%Y-%m-%d %H:%M:%S')"
    else
      log "weekend_noon called on weekday (dow=$DOW) — skip"
      exit 0
    fi
    ;;
  *)
    usage
    ;;
esac

log "slot=$SLOT wake=$WAKE starting rtcwake+poweroff"

if ! sudo -n true 2>/dev/null; then
  log "ERROR: passwordless sudo missing — run: sudo bash ${SCRIPT_DIR}/install-power-schedule-sudo.sh"
  exit 1
fi

RTCWAKE="$(command -v rtcwake)"

if sudo -n "$RTCWAKE" -m off --date "$WAKE" >>"$LOG_FILE" 2>&1; then
  log "rtcwake -m off --date '$WAKE' OK (system powering off)"
  exit 0
fi

log "WARN: rtcwake failed — falling back to shutdown without wake alarm"
sudo -n "$(command -v shutdown)" -h now "power-schedule ${SLOT}" >>"$LOG_FILE" 2>&1 || \
  sudo -n systemctl poweroff >>"$LOG_FILE" 2>&1
log "shutdown issued"
