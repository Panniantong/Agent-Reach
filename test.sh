#!/bin/bash
# Agent Reach 一键完整测试
# 用法: bash test-agent-reach.sh
# 在任何有 Python 3.10+ 的机器上跑就行

set -e

echo "╔════════════════════════════════════════════╗"
echo "║    👁️  Agent Reach 完整测试                ║"
echo "╚════════════════════════════════════════════╝"
echo ""

# ── 1. 准备干净环境 ──
echo "📦 创建测试环境..."
TEST_DIR=$(mktemp -d)
python3 -m venv "$TEST_DIR/venv"
source "$TEST_DIR/venv/bin/activate"

# ── 2. 安装 ──
echo "📥 从 GitHub 安装..."
pip install -q https://github.com/Panniantong/agent-reach/archive/v1.5.0.zip 2>&1 | tail -1
echo ""

# ── 3. 自动配置 ──
echo "⚙️  运行 install..."
agent-reach install --env=auto 2>&1
echo ""

# ── 4. 诊断 ──
echo "🩺 运行 doctor..."
agent-reach doctor 2>&1
echo ""

# ── 5. 逐个测试 ──
PASS=0
FAIL=0
SKIP=0

test_it() {
    local name="$1"
    shift
    echo -n "  $name ... "
    output=$(eval "$@" 2>&1) || true
    if echo "$output" | grep -q "📖\|🔗\|http"; then
        echo "✅"
        PASS=$((PASS+1))
    elif echo "$output" | grep -q "⚠️\|not installed\|not configured"; then
        echo "⏭️  (跳过 — 缺依赖)"
        SKIP=$((SKIP+1))
    else
        echo "❌"
        echo "    $(echo "$output" | head -2)"
        FAIL=$((FAIL+1))
    fi
}

echo "📖 阅读测试"
test_it "网页" "agent-reach read 'https://example.com'"
test_it "GitHub" "agent-reach read 'https://github.com/Panniantong/agent-reach'"
test_it "YouTube" "agent-reach read 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'"
test_it "B站" "agent-reach read 'https://www.bilibili.com/video/BV1d4411N7zD'"
test_it "RSS" "agent-reach read 'https://hnrss.org/frontpage'"
test_it "Twitter" "agent-reach read 'https://x.com/elonmusk/status/1893797839927353448'"
test_it "Reddit" "agent-reach read 'https://www.reddit.com/r/LocalLLaMA/hot'"

echo ""
echo "🔍 搜索测试"
test_it "全网搜索" "agent-reach search 'best AI agent framework' -n 2"
test_it "GitHub搜索" "agent-reach search-github 'yt-dlp' -n 2"
test_it "Twitter搜索" "agent-reach search-twitter 'AI agent' -n 2"
test_it "Reddit搜索" "agent-reach search-reddit 'machine learning' -n 2"
test_it "YouTube搜索" "agent-reach search-youtube 'AI tutorial' -n 2"
test_it "B站搜索" "agent-reach search-bilibili 'AI' -n 2"
test_it "小红书搜索" "agent-reach search-xhs 'AI' -n 2"

echo ""
echo "════════════════════════════════════════════"
echo "  ✅ 通过: $PASS   ❌ 失败: $FAIL   ⏭️  跳过: $SKIP"
echo "════════════════════════════════════════════"

# ── 6. 清理 ──
deactivate 2>/dev/null || true
rm -rf "$TEST_DIR"

if [ $FAIL -eq 0 ]; then
    echo ""
    echo "🎉 全部通过！"
else
    echo ""
    echo "⚠️  有 $FAIL 个测试失败，请检查上面的输出"
    exit 1
fi
