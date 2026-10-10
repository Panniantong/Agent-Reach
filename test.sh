#!/bin/bash
# Agent Reach clean-environment integration test.
# Creates an isolated venv, installs this checkout, runs a read-only doctor,
# then executes the repository test suite.

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
if command -v python3 >/dev/null 2>&1 && \
   python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)'; then
    PYTHON_CMD=(python3)
elif command -v python >/dev/null 2>&1 && \
     python -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)'; then
    PYTHON_CMD=(python)
elif command -v py >/dev/null 2>&1 && \
     py -3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)'; then
    PYTHON_CMD=(py -3)
elif [ -x "$REPO_ROOT/.venv/bin/python" ] && \
     "$REPO_ROOT/.venv/bin/python" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)'; then
    PYTHON_CMD=("$REPO_ROOT/.venv/bin/python")
elif [ -x "$REPO_ROOT/.venv/Scripts/python.exe" ] && \
     "$REPO_ROOT/.venv/Scripts/python.exe" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)'; then
    PYTHON_CMD=("$REPO_ROOT/.venv/Scripts/python.exe")
else
    echo "Python 3.10+ is required" >&2
    exit 1
fi

echo "[1/5] Creating isolated environment"
"${PYTHON_CMD[@]}" -m venv "$TEST_DIR/venv"
# shellcheck disable=SC1091
if [ -f "$TEST_DIR/venv/bin/activate" ]; then
    source "$TEST_DIR/venv/bin/activate"
elif [ -f "$TEST_DIR/venv/Scripts/activate" ]; then
    source "$TEST_DIR/venv/Scripts/activate"
else
    echo "Could not find the virtual environment activation script" >&2
    exit 1
fi

echo "[2/5] Installing this checkout and test dependencies"
python -m pip install --quiet --upgrade pip
# Install the editable target from a subshell cd'd into the repo with a
# relative ".[dev]". On Windows (Git Bash + native Python), an absolute
# "$REPO_ROOT[dev]" defeats MSYS path conversion: the trailing [dev] makes
# the argument look like a non-existent path, so the "/d/..." form is
# passed through unchanged and native pip rejects it as "not a valid
# editable requirement". A relative path avoids the conversion. The
# constraints path is kept absolute on purpose: the file exists, so MSYS
# converts it cleanly, and test_integration_script pins that exact spelling.
( cd "$REPO_ROOT" && python -m pip install --quiet -c "$REPO_ROOT/constraints.txt" -e ".[dev]" )

echo "[3/5] Verifying the installed CLI"
agent-reach version

echo "[4/5] Running read-only install check and doctor"
agent-reach install --env=auto --safe
agent-reach install --env=auto --system --dry-run
agent-reach doctor --json > "$TEST_DIR/doctor.json"
python -c 'import json,sys; data=json.load(open(sys.argv[1], encoding="utf-8")); assert isinstance(data, dict) and data, "doctor returned no channels"; print(f"doctor OK: {len(data)} channels")' "$TEST_DIR/doctor.json"

echo "[5/5] Running repository tests"
pytest "$REPO_ROOT/tests" -q

echo "Agent Reach integration test passed"
