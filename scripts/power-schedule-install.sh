#!/usr/bin/env bash
# Install local power-on/off crontab (Asia/Shanghai).
#
# Schedule:
#   Mon–Fri: 06:40 boot (rtcwake) · 11:40 off → 12:40 boot · 16:00 off → next boot
#   Sat/Sun: 08:40 boot (rtcwake) · 12:00 off → next boot
#
# Also run once: sudo bash scripts/install-power-schedule-sudo.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT="${REPO_ROOT}/scripts/power-schedule.sh"
MARKER_BEGIN="# agent-reach power-schedule BEGIN"
MARKER_END="# agent-reach power-schedule END"

chmod +x "$SCRIPT" "${REPO_ROOT}/scripts/install-power-schedule-sudo.sh"

BLOCK=$(cat <<EOF
${MARKER_BEGIN}
SHELL=/bin/bash
CRON_TZ=Asia/Shanghai
# log: ~/.agent-reach/daily_run/logs/power-schedule-YYYY-MM-DD.log
# script: ${SCRIPT}
40 11 * * 1-5 ${SCRIPT} lunch  # 11:40 off → wake 12:40
0 16 * * 1-5 ${SCRIPT} weekday_pm  # 16:00 off → wake next 06:40 (Fri→Sat 08:40)
0 12 * * 6 ${SCRIPT} weekend_noon  # Sat 12:00 off → wake Sun 08:40
0 12 * * 0 ${SCRIPT} weekend_noon  # Sun 12:00 off → wake Mon 06:40
${MARKER_END}
EOF
)

if ! command -v crontab >/dev/null 2>&1; then
  OUT="${HOME}/.agent-reach/daily_run/crontab-power-schedule.txt"
  mkdir -p "$(dirname "$OUT")"
  printf '%s\n' "$BLOCK" >"$OUT"
  echo "❌ crontab not found; wrote ${OUT} — install manually"
  exit 1
fi

existing="$(crontab -l 2>/dev/null || true)"
before=""
after=""
if echo "$existing" | grep -qF "$MARKER_BEGIN"; then
  before="$(echo "$existing" | sed "/${MARKER_BEGIN}/,/${MARKER_END}/d" | sed -e :a -e '/^\n*$/{$d;N;ba' -e '}')"
  after=""
fi

new_crontab="$before"
[ -n "$new_crontab" ] && new_crontab="${new_crontab}"$'\n'
new_crontab="${new_crontab}${BLOCK}"
[ -n "$after" ] && new_crontab="${new_crontab}"$'\n'"${after}"

printf '%s\n' "$new_crontab" | crontab -

echo "✅ Power schedule crontab installed (Asia/Shanghai)"
echo "   Mon–Fri: 11:40 off→12:40 on · 16:00 off→next morning on"
echo "   Sat/Sun: 12:00 off→next session on"
echo "   Boot times use rtcwake at shutdown (06:40 / 08:40 / 12:40)"
echo
echo "⚠️  Run once if not done: sudo bash ${REPO_ROOT}/scripts/install-power-schedule-sudo.sh"
echo "⚠️  KVM/VM: if rtcwake does not wake the guest, configure host VM autostart at those times"
