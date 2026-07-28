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

echo "✅ Sudoers: ${SUDOERS}"
echo "   Test as ${USER_NAME}: sudo -n ${SCHEDULE_SCRIPT} lunch  # will power off — don't run now"
echo "   Verify: sudo -n rtcwake -m show"
