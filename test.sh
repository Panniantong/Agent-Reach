#!/bin/bash
# Agent Reach one-command full test
# Usage: bash test-agent-reach.sh
# Run it on any machine with Python 3.10+

set -e

echo "╔════════════════════════════════════════════╗"
echo "║    👁️  Agent Reach full test               ║"
echo "╚════════════════════════════════════════════╝"
echo ""

# ── 1. Prepare a clean environment ──
echo "📦 Creating test environment..."
TEST_DIR=$(mktemp -d)
python3 -m venv "$TEST_DIR/venv"
source "$TEST_DIR/venv/bin/activate"

# ── 2. Install ──
echo "📥 Installing from GitHub..."
pip install -q https://github.com/Panniantong/agent-reach/archive/main.zip 2>&1 | tail -1
echo ""

# ── 3. Auto-configure ──
echo "⚙️  Running install..."
agent-reach install --env=auto 2>&1
echo ""

# ── 4. Diagnostics ──
echo "🩺 Running doctor..."
agent-reach doctor 2>&1
echo ""

# ── 5. Test one by one ──
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
        echo "⏭️  (Skipped — missing dependency)"
        SKIP=$((SKIP+1))
    else
        echo "❌"
        echo "    $(echo "$output" | head -2)"
        FAIL=$((FAIL+1))
    fi
}

echo "📖 Read tests"
test_it "Web" "agent-reach read 'https://example.com'"
test_it "GitHub" "agent-reach read 'https://github.com/Panniantong/agent-reach'"
test_it "YouTube" "agent-reach read 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'"
test_it "Bilibili" "agent-reach read 'https://www.bilibili.com/video/BV1d4411N7zD'"
test_it "RSS" "agent-reach read 'https://hnrss.org/frontpage'"
test_it "Twitter" "agent-reach read 'https://x.com/elonmusk/status/1893797839927353448'"
test_it "Reddit" "agent-reach read 'https://www.reddit.com/r/LocalLLaMA/hot'"

echo ""
echo "🔍 Search tests"
test_it "Web search" "agent-reach search 'best AI agent framework' -n 2"
test_it "GitHub search" "agent-reach search-github 'yt-dlp' -n 2"
test_it "Twitter search" "agent-reach search-twitter 'AI agent' -n 2"
test_it "Reddit search" "agent-reach search-reddit 'machine learning' -n 2"
test_it "YouTube search" "agent-reach search-youtube 'AI tutorial' -n 2"
test_it "Bilibili search" "agent-reach search-bilibili 'AI' -n 2"
test_it "XiaoHongShu search" "agent-reach search-xhs 'AI' -n 2"

echo ""
echo "════════════════════════════════════════════"
echo "  ✅ Passed: $PASS   ❌ Failed: $FAIL   ⏭️  Skipped: $SKIP"
echo "════════════════════════════════════════════"

# ── 6. Cleanup ──
deactivate 2>/dev/null || true
rm -rf "$TEST_DIR"

if [ $FAIL -eq 0 ]; then
    echo ""
    echo "🎉 All passed!"
else
    echo ""
    echo "⚠️  $FAIL test(s) failed, please check the output above"
    exit 1
fi
