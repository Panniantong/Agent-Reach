#!/usr/bin/env bash
# Agent Reach smoke test
# Usage: bash test.sh
# Creates a clean virtualenv, installs the current checkout, and verifies the
# supported CLI contract: installer, doctor, version, and Python API.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEST_DIR="$(mktemp -d)"
trap 'deactivate 2>/dev/null || true; rm -rf "$TEST_DIR"' EXIT

echo "╔════════════════════════════════════════════╗"
echo "║    👁️  Agent Reach smoke test             ║"
echo "╚════════════════════════════════════════════╝"
echo

echo "📦 Creating clean test environment..."
python3 -m venv "$TEST_DIR/venv"
# shellcheck disable=SC1091
source "$TEST_DIR/venv/bin/activate"
python -m pip install -q --upgrade pip

echo "📥 Installing current checkout..."
pip install -q -e "$ROOT_DIR[dev]"

echo "🔢 Version..."
agent-reach version

echo "⚙️  Installer dry-run..."
agent-reach install --env=auto --dry-run >/tmp/agent-reach-install-dry-run.txt
head -20 /tmp/agent-reach-install-dry-run.txt

echo "🩺 Doctor JSON..."
agent-reach doctor --json > "$TEST_DIR/doctor.json"
python -m json.tool "$TEST_DIR/doctor.json" >/dev/null
python - <<'PY' "$TEST_DIR/doctor.json"
import json, sys
with open(sys.argv[1], encoding="utf-8") as f:
    data = json.load(f)
required = {"github", "youtube", "web", "rss"}
missing = sorted(required - set(data))
if missing:
    raise SystemExit(f"missing expected channels: {missing}")
ok = sum(1 for item in data.values() if item.get("status") == "ok")
print(f"doctor reported {ok}/{len(data)} channels active")
PY

echo "🐍 Python API..."
python - <<'PY'
from agent_reach import AgentReach
report = AgentReach().doctor()
assert isinstance(report, dict)
assert "github" in report
print(f"AgentReach().doctor() returned {len(report)} channels")
PY

echo

echo "🎉 Smoke test passed"
