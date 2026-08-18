#!/usr/bin/env bash
# Scheduled power-off with RTC wake for the next session window.
# Boot times (06:40 / 08:00 / 12:40) are set via rtcwake when shutting down.
#
# Slots (Asia/Shanghai):
#   lunch     Mon–Fri 12:00 off → wake 12:40 same day
#   midnight  Every day 00:00 off →
#             Mon 00:00 (end Sun)   → wake Mon 06:40
#             Tue–Fri 00:00         → wake same day 06:40 (end Mon–Thu)
#             Sat 00:00 (end Fri)   → wake Sat 08:00
#             Sun 00:00 (end Sat)   → wake Sun 08:00
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
  echo "usage: $(basename "$0") lunch|midnight" >&2
  exit 2
}

SLOT="${1:-}"
case "$SLOT" in
  lunch)
    DOW="$(date +%u)"
    if [ "$DOW" -gt 5 ]; then
      log "lunch called on weekend (dow=$DOW) — skip"
      exit 0
    fi
    WAKE="$(date -d 'today 12:40' '+%Y-%m-%d %H:%M:%S')"
    ;;
  midnight)
    DOW="$(date +%u)"
    case "$DOW" in
      1) WAKE="$(date -d 'today 06:40' '+%Y-%m-%d %H:%M:%S')" ;;
      2|3|4|5) WAKE="$(date -d 'today 06:40' '+%Y-%m-%d %H:%M:%S')" ;;
      6|7) WAKE="$(date -d 'today 08:00' '+%Y-%m-%d %H:%M:%S')" ;;
      *)
        log "midnight unexpected dow=$DOW — skip"
        exit 0
        ;;
    esac
    ;;
  *)
    usage
    ;;
esac

log "slot=$SLOT wake=$WAKE starting rtcwake+poweroff"

RTCWAKE="$(command -v rtcwake || true)"
if [ -z "$RTCWAKE" ]; then
  log "ERROR: rtcwake not found — install util-linux / linux-tools"
  exit 1
fi

# sudoers only whitelists rtcwake/shutdown/poweroff — not bare `sudo true`.
if ! sudo -n "$RTCWAKE" -m show >>"$LOG_FILE" 2>&1; then
  log "ERROR: passwordless sudo missing for rtcwake — run: sudo bash ${SCRIPT_DIR}/install-power-schedule-sudo.sh"
  exit 1
fi

if sudo -n "$RTCWAKE" -m off --date "$WAKE" >>"$LOG_FILE" 2>&1; then
  log "rtcwake -m off --date '$WAKE' OK (system powering off)"
  exit 0
fi

log "WARN: rtcwake failed — falling back to shutdown without wake alarm"
sudo -n "$(command -v shutdown)" -h now "power-schedule ${SLOT}" >>"$LOG_FILE" 2>&1 || \
  sudo -n systemctl poweroff >>"$LOG_FILE" 2>&1
log "shutdown issued"
