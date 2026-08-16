#!/usr/bin/env bash
# Map 北京时间 wall clock (or workflow_dispatch / cron schedule) to daily-run job name.
set -euo pipefail

export TZ="${TZ:-Asia/Shanghai}"

if [ "${GITHUB_EVENT_NAME:-}" = "workflow_dispatch" ]; then
  job="${INPUT_JOB:-intraday}"
  echo "job=${job}"
  echo "skip=false"
  exit 0
fi

# Prefer the cron expression that triggered this run (GitHub Actions timezone-aware schedule).
if [ -n "${GITHUB_EVENT_SCHEDULE:-}" ]; then
  case "${GITHUB_EVENT_SCHEDULE}" in
    "0 8 * * 1-5")
      echo "job=morning"
      echo "skip=false"
      exit 0
      ;;
    "30 15 * * 1-5")
      echo "job=close"
      echo "skip=false"
      exit 0
      ;;
    "0 18 * * 1-5")
      echo "job=close"
      echo "skip=false"
      exit 0
      ;;
    "0 9 * * 6")
      echo "job=weekly"
      echo "skip=false"
      exit 0
      ;;
    "30 8 * * 6")
      echo "job=weekly"
      echo "skip=false"
      exit 0
      ;;
    "0 10 * * 6")
      echo "job=weekly"
      echo "skip=false"
      exit 0
      ;;
    "0 9 * * 0")
      echo "job=forecast"
      echo "skip=false"
      exit 0
      ;;
    "30 8 * * 0")
      echo "job=forecast"
      echo "skip=false"
      exit 0
      ;;
    "30 8 * * 1-5"|"0 9 * * 1-5"|\
    "30 9 * * 1-5"|"54 9 * * 1-5"|\
    "18 10 * * 1-5"|"42 10 * * 1-5"|"6 11 * * 1-5"|"30 11 * * 1-5"|\
    "0 13 * * 1-5"|"24 13 * * 1-5"|"48 13 * * 1-5"|\
    "12 14 * * 1-5"|"36 14 * * 1-5"|"0 15 * * 1-5")
      echo "job=intraday"
      echo "skip=false"
      exit 0
      ;;
  esac
fi

h=$(date +%H)
m=$(date +%M)
h=$((10#$h))
m=$((10#$m))
minutes=$((h * 60 + m))

# Morning window ~08:00 北京时间 (allow GitHub schedule delay).
if [ "$minutes" -ge 470 ] && [ "$minutes" -le 520 ]; then
  echo "job=morning"
  echo "skip=false"
  exit 0
fi

# Close window ~18:00 北京时间.
if [ "$minutes" -ge 1060 ] && [ "$minutes" -le 1110 ]; then
  echo "job=close"
  echo "skip=false"
  exit 0
fi

# Weekly report ~08:30 北京时间 Saturday.
if [ "$(date +%u)" = "6" ] && [ "$minutes" -ge 500 ] && [ "$minutes" -le 540 ]; then
  echo "job=weekly"
  echo "skip=false"
  exit 0
fi

# Next-week forecast ~08:30 北京时间 Sunday.
if [ "$(date +%u)" = "7" ] && [ "$minutes" -ge 500 ] && [ "$minutes" -le 540 ]; then
  echo "job=forecast"
  echo "skip=false"
  exit 0
fi

# Intraday scans ~08:25–15:05 北京时间.
if [ "$minutes" -ge 505 ] && [ "$minutes" -le 905 ]; then
  echo "job=intraday"
  echo "skip=false"
  exit 0
fi

echo "job=intraday"
echo "skip=true"
