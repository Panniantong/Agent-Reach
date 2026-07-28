#!/usr/bin/env bash
# Install local power-on/off crontab (Asia/Shanghai).
#
# Schedule (boot via rtcwake at prior shutdown):
#   Mon–Fri: 06:40 on · 12:00 off → 12:40 on · 00:00 off → next on
#   Sat/Sun: 08:00 on · 00:00 off → next on
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
0 12 * * 1-5 ${SCRIPT} lunch  # 12:00 off → wake 12:40
0 0 * * * ${SCRIPT} midnight  # 00:00 off → wake 06:40 (Mon–Fri) or 08:00 (Sat/Sun)
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
echo "   Mon–Fri: 06:40 on · 12:00 off→12:40 on · 00:00 off→next 06:40 (Fri→Sat 08:00)"
echo "   Sat/Sun: 08:00 on · 00:00 off→next 08:00 (Sun→Mon 06:40)"
echo "   Boot times use rtcwake at shutdown"
echo
echo "⚠️  Run once if not done: sudo bash ${REPO_ROOT}/scripts/install-power-schedule-sudo.sh"
echo "⚠️  KVM/VM: if rtcwake does not wake the guest, configure host VM autostart at those times"
