#!/usr/bin/env bash
# Enable kernel crash dump capture (requires sudo once).
# After setup: vmcores land in /var/crash/ on panic/hard reset with kdump.
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "Run with sudo: sudo bash $0" >&2
  exit 1
fi

if ! dpkg -s kdump-tools >/dev/null 2>&1; then
  apt-get update -qq
  apt-get install -y kdump-tools
fi

sed -i 's/^USE_KDUMP=.*/USE_KDUMP=1/' /etc/default/kdump-tools
grep -q '^KDUMP_NUM_DUMPS=' /etc/default/kdump-tools || \
  echo 'KDUMP_NUM_DUMPS="3"' >> /etc/default/kdump-tools
sed -i 's/^#KDUMP_NUM_DUMPS=.*/KDUMP_NUM_DUMPS="3"/' /etc/default/kdump-tools

kdump-config load
kdump-config show || true
status="$(kdump-config status 2>&1 || true)"
echo "$status"
if echo "$status" | grep -qi 'ready to kdump'; then
  echo "✅ kdump ready — next kernel crash will save vmcore to /var/crash/"
else
  echo "⚠️ kdump not fully ready; check: kdump-config status"
  exit 1
fi
