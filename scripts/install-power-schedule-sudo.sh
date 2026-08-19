#!/usr/bin/env bash
# One-time: passwordless rtcwake + shutdown for power-schedule cron.
set -euo pipefail

USER_NAME="${SUDO_USER:-${USER:-zjk}}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCHEDULE_SCRIPT="${REPO_ROOT}/scripts/power-schedule.sh"
SUDOERS="/etc/sudoers.d/agent-reach-power-schedule"

if [ "$(id -u)" -ne 0 ]; then
  echo "Run with sudo: sudo bash $0" >&2
  exit 1
fi

chmod +x "$SCHEDULE_SCRIPT"

tee "$SUDOERS" >/dev/null <<EOF
# Agent Reach power schedule (cron shutdown + rtcwake)
${USER_NAME} ALL=(ALL) NOPASSWD: ${SCHEDULE_SCRIPT}
${USER_NAME} ALL=(ALL) NOPASSWD: /usr/sbin/rtcwake, /sbin/rtcwake
${USER_NAME} ALL=(ALL) NOPASSWD: /sbin/shutdown, /usr/sbin/shutdown
${USER_NAME} ALL=(ALL) NOPASSWD: /bin/systemctl poweroff, /usr/bin/systemctl poweroff
EOF
chmod 440 "$SUDOERS"
visudo -cf "$SUDOERS"

RTCWAKE="$(command -v rtcwake || true)"
if [ -z "$RTCWAKE" ]; then
  echo "⚠️  rtcwake not on PATH; sudoers installed but wake scheduling may fail" >&2
elif ! sudo -u "${USER_NAME}" sudo -n "$RTCWAKE" -m show >/dev/null 2>&1; then
  echo "❌ visudo OK but passwordless rtcwake failed for ${USER_NAME}" >&2
  echo "   Check ${SUDOERS} and re-run this script" >&2
  exit 1
fi

echo "✅ Sudoers: ${SUDOERS}"
echo "   Verified: sudo -n rtcwake -m show (as ${USER_NAME})"
echo "   Do not test lunch/midnight here — those power off the machine"
