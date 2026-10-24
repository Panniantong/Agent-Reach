#!/bin/bash
# Agent Reach clean-environment integration test.
# Creates an isolated venv and HOME, installs this checkout, runs the
# read-only CLI commands, then executes the repository test suite.

set -euo pipefail

REPO_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
TEST_DIR=$(mktemp -d "${TMPDIR:-/tmp}/agent-reach-test.XXXXXX")
TEST_DIR=$(cd "$TEST_DIR" && pwd -P)
export HOME="$TEST_DIR/home"
export XDG_CONFIG_HOME="$HOME/.config"
export PYTHONDONTWRITEBYTECODE=1
mkdir -p "$HOME" "$XDG_CONFIG_HOME"

cleanup() {
    rm -rf -- "$TEST_DIR"
}
trap cleanup EXIT INT TERM

PYTHON_CMD=()
for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 && \
       "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)'; then
        PYTHON_CMD=("$candidate")
        break
    fi
done
if [ ${#PYTHON_CMD[@]} -eq 0 ] && command -v py >/dev/null 2>&1 && \
   py -3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)'; then
    PYTHON_CMD=(py -3)
fi
if [ ${#PYTHON_CMD[@]} -eq 0 ]; then
    echo "Python 3.10+ is required" >&2
    exit 1
fi

echo "[1/4] Creating isolated environment"
"${PYTHON_CMD[@]}" -m venv "$TEST_DIR/venv"
# shellcheck disable=SC1091
if [ -f "$TEST_DIR/venv/bin/activate" ]; then
    source "$TEST_DIR/venv/bin/activate"
else
    source "$TEST_DIR/venv/Scripts/activate"
fi

echo "[2/4] Installing this checkout and test dependencies"
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -c "$REPO_ROOT/constraints.txt" -e "$REPO_ROOT[dev]"

echo "[3/4] Running read-only CLI commands"
agent-reach version
agent-reach channels > "$TEST_DIR/channels.json"
python -c 'import json,sys; d=json.load(open(sys.argv[1], encoding="utf-8")); assert d["ok"] and d["channels"], d; print(f"channels OK: {len(d[\"channels\"])}")' "$TEST_DIR/channels.json"
agent-reach doctor > "$TEST_DIR/doctor.json"
python -c 'import json,sys; d=json.load(open(sys.argv[1], encoding="utf-8")); assert "ok" in d, d; print("doctor OK")' "$TEST_DIR/doctor.json"

echo "[4/4] Running repository tests"
pytest "$REPO_ROOT/tests" -q

echo "Agent Reach integration test passed"
