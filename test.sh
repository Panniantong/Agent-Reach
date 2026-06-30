#!/bin/bash
# Agent Reach 一键完整测试
# 用法: bash test.sh
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
pip install -q https://github.com/Panniantong/agent-reach/archive/main.zip 2>&1 | tail -1
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

# Success: output looks meaningful (not empty, not just a usage/error message)
# Skip: auth-required channels that report warn/off/not-installed
# Fail: anything else (empty output, crash, unexpected error)

test_it() {
    local name="$1"
    local expected="$2"   # "always" | "if_installed" | "skip_if_off"
    shift 2
    echo -n "  $name ... "
    output=$(eval "$@" 2>&1) || true

    case "$expected" in
        always)
            # Should always produce useful output
            if [ -z "$output" ] || echo "$output" | grep -qiE "^(usage:|error:|fatal:)"; then
                echo "❌"
                echo "    $(echo "$output" | head -2)"
                FAIL=$((FAIL+1))
            else
                echo "✅"
                PASS=$((PASS+1))
            fi
            ;;
        if_installed)
            # Auth/optional — succeed if output looks good, skip if not installed
            if echo "$output" | grep -qiE "(not installed|not configured|^off |unavailable|no .* backend|missing)"; then
                echo "⏭️  (跳过 — 需配置)"
                SKIP=$((SKIP+1))
            elif [ -z "$output" ]; then
                echo "❌"
                echo "    (empty output)"
                FAIL=$((FAIL+1))
            else
                echo "✅"
                PASS=$((PASS+1))
            fi
            ;;
        *)
            echo "❌ (internal: bad expected=$expected)"
            FAIL=$((FAIL+1))
            ;;
    esac
}

echo "📖 阅读测试 (零配置渠道)"
test_it "网页 (Jina)"  always "curl -sS 'https://r.jina.ai/https://example.com' 2>&1 | head -3"
test_it "GitHub (gh CLI)" always "gh repo view Panniantong/agent-reach --json name 2>&1"
test_it "YouTube (yt-dlp)" always "yt-dlp --print title 'https://www.youtube.com/watch?v=dQw4w9WgXcQ' 2>&1"
test_it "RSS (feedparser)" always "python3 -c \"import feedparser; d=feedparser.parse('https://hnrss.org/frontpage'); print(len(d.entries), 'entries')\""
test_it "V2EX (热门)"   always "python3 -c \"from agent_reach.channels.v2ex import V2EXChannel; c=V2EXChannel(); t=c.get_hot_topics(2); print(len(t), 'topics')\""
test_it "B站 (搜索API)" always "python3 -c \"
import json,urllib.request
r=urllib.request.urlopen(urllib.request.Request(
    'https://api.bilibili.com/x/web-interface/search/all/v2?keyword=test&page=1',
    headers={'User-Agent':'Mozilla/5.0'}))
d=json.load(r)
print('OK code=0' if d.get('code')==0 else 'FAIL code='+str(d.get('code')))
\""

echo ""
echo "🔍 搜索测试 (零配置渠道)"
test_it "全网搜索 (Exa)"   always "python3 -c \"
from agent_reach.channels.exa_search import ExaSearchChannel
c=ExaSearchChannel(); s,m=c.check(); print(s,':', m[:100])
\""
test_it "GitHub搜索"      always "gh search repos 'yt-dlp' --limit 2 --json name 2>&1 | head -3"
test_it "YouTube搜索"     always "yt-dlp --flat-playlist --print title 'ytsearch2:AI tutorial' 2>&1 | head -3"
test_it "B站搜索"         always "python3 -c \"
import json,urllib.request
r=urllib.request.urlopen(urllib.request.Request(
    'https://api.bilibili.com/x/web-interface/search/all/v2?keyword=AI&page=1',
    headers={'User-Agent':'Mozilla/5.0'}))
d=json.load(r)
n=len(d.get('data',{}).get('result',[]))
print(n,'result categories' if d.get('code')==0 else 'FAIL')
\""

echo ""
echo "🔐 需认证渠道 (状态检查)"
test_it "Twitter/X"  if_installed "python3 -c \"from agent_reach.channels.twitter import TwitterChannel; c=TwitterChannel(); s,m=c.check(); print(s,':', m[:100])\""
test_it "Reddit"     if_installed "python3 -c \"from agent_reach.channels.reddit import RedditChannel; c=RedditChannel(); s,m=c.check(); print(s,':', m[:100])\""
test_it "小红书"     if_installed "python3 -c \"from agent_reach.channels.xiaohongshu import XiaoHongShuChannel; c=XiaoHongShuChannel(); s,m=c.check(); print(s,':', m[:100])\""
test_it "雪球"       if_installed "python3 -c \"from agent_reach.channels.xueqiu import XueqiuChannel; c=XueqiuChannel(); s,m=c.check(); print(s,':', m[:100])\""
test_it "LinkedIn"   if_installed "python3 -c \"from agent_reach.channels.linkedin import LinkedInChannel; c=LinkedInChannel(); s,m=c.check(); print(s,':', m[:100])\""
test_it "小宇宙播客" if_installed "python3 -c \"from agent_reach.channels.xiaoyuzhou import XiaoyuzhouChannel; c=XiaoyuzhouChannel(); s,m=c.check(); print(s,':', m[:100])\""

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
