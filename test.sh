#!/bin/bash
# Agent Reach 安装冒烟测试 / install smoke test
# 用法: bash test.sh
#
# 需要 Python 3.10+。在一个干净的临时 venv 里安装本仓库的本地工作副本，
# 验证打包 + 入口命令 + doctor 能真正跑起来（pip editable 装法测不到这些）。
# 注意：Agent Reach 是安装器/诊断器，不是 wrapper —— 装好后 Agent 直接调用上游
# 工具，没有 `agent-reach read/search` 之类子命令。确定性单元测试请跑
# `pytest tests/ -v`。

set -euo pipefail

# 脚本所在目录 = 仓库根，用于安装本地工作副本
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "╔════════════════════════════════════════════╗"
echo "║    👁️  Agent Reach 安装冒烟测试            ║"
echo "╚════════════════════════════════════════════╝"
echo ""

# ── 1. 干净的临时环境 ──
echo "📦 创建临时 venv..."
TEST_DIR=$(mktemp -d)
cleanup() { deactivate 2>/dev/null || true; rm -rf "$TEST_DIR"; }
trap cleanup EXIT
python3 -m venv "$TEST_DIR/venv"
# shellcheck disable=SC1091
source "$TEST_DIR/venv/bin/activate"

# ── 2. 从本地工作副本安装 ──
echo "📥 安装本地工作副本..."
pip install -q "$SCRIPT_DIR" 2>&1 | tail -1
echo ""

# ── 3. 冒烟检查：入口命令存在并可执行 ──
FAIL=0
check() {
    local name="$1"; shift
    echo -n "  $name ... "
    if "$@" >/dev/null 2>&1; then
        echo "✅"
    else
        echo "❌"
        FAIL=$((FAIL + 1))
    fi
}

echo "🔎 入口命令冒烟检查"
check "version"      agent-reach version
check "--help"       agent-reach --help
check "doctor"       agent-reach doctor
check "install dry"  agent-reach install --dry-run

echo ""
echo "🩺 doctor 完整输出："
agent-reach doctor 2>&1 || true

echo ""
echo "════════════════════════════════════════════"
if [ "$FAIL" -eq 0 ]; then
    echo "  🎉 安装冒烟测试通过"
    echo "  提示：确定性单元测试请跑 pytest tests/ -v"
    echo "════════════════════════════════════════════"
else
    echo "  ⚠️  有 $FAIL 项冒烟检查失败，请检查上面的输出"
    echo "════════════════════════════════════════════"
    exit 1
fi
