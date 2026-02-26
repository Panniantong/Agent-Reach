---
name: agent-reach
description: >
  Give your AI agent eyes to see the entire internet. Install and configure
  upstream tools for Twitter/X, Reddit, YouTube, GitHub, Bilibili, XiaoHongShu,
  Douyin, LinkedIn, Boss直聘, RSS, and any web page — then call them directly.
  Use when: (1) setting up platform access tools for the first time,
  (2) checking which platforms are available,
  (3) user asks to configure/enable a platform channel.
  Triggers: "帮我配", "帮我添加", "帮我安装", "agent reach", "install channels",
  "configure twitter", "enable reddit".
---

# Agent Reach

Install and configure upstream tools for 12+ platforms. After setup, call them directly — no wrapper layer.

## Setup

```bash
pip install https://github.com/Panniantong/agent-reach/archive/main.zip
agent-reach install --env=auto
agent-reach doctor
```

`install` auto-detects your environment and installs core dependencies (Node.js, mcporter, bird CLI, gh CLI, yt-dlp, feedparser). Run `doctor` to see what's active.

## Management

```bash
agent-reach doctor        # channel status overview
agent-reach watch         # quick health + update check
agent-reach check-update  # check for new versions
```

## Configure channels

```bash
agent-reach configure twitter-cookies "auth_token=xxx; ct0=yyy"
agent-reach configure proxy http://user:pass@ip:port
agent-reach configure --from-browser chrome    # auto-extract cookies from local browser
```

## Configuring a channel ("帮我配 XXX")

When a user asks to configure/enable any channel:

1. Run `agent-reach doctor`
2. Find the channel — it shows status (✅/⚠️/⬜) and **what to do next**
3. Execute what you can automatically (install packages, start services)
4. For human-required steps (paste cookies), tell the user what to do
5. Run `agent-reach doctor` again to verify

**Do NOT memorize per-channel steps.** Always rely on `doctor` output.

### Cookie 导入（所有需要登录的平台通用）

> ⚠️ **重要提醒：** 使用 Cookie 登录的平台存在封号风险，请提醒用户务必使用**专用小号**。

所有需要 Cookie 的平台（Twitter、小红书等），**优先使用 Cookie-Editor 导入**：

1. 用户在自己的浏览器登录对应平台
2. 安装 [Cookie-Editor](https://chromewebstore.google.com/detail/cookie-editor/hlkenndednhfkekhgcdicdfddnkalmdm) Chrome 插件
3. 点击插件 → Export → Header String
4. 把导出的字符串发给 Agent

本地电脑用户也可以用 `agent-reach configure --from-browser chrome` 一键自动提取。

扫码登录是备选方案（仅限本地有浏览器的情况），Cookie-Editor 更简单可靠。

### Other human actions

- **Proxy:** Reddit/Bilibili/XiaoHongShu may block server IPs — suggest a residential proxy if on a server

---

## Using Upstream Tools Directly

After `agent-reach install`, call the upstream tools directly. No need for `agent-reach read` or `agent-reach search`.

### Twitter/X (bird CLI)

```bash
# Search tweets
bird search "query" --json -n 10

# Read a specific tweet
bird read https://x.com/user/status/123 --json

# Read a user's timeline
bird timeline @username --json -n 20
```

### YouTube (yt-dlp)

```bash
# Get video metadata
yt-dlp --dump-json "https://www.youtube.com/watch?v=xxx"

# Download subtitles only
yt-dlp --write-sub --write-auto-sub --sub-lang "zh-Hans,zh,en" --skip-download -o "/tmp/%(id)s" "URL"
# Then read the .vtt file

# Search (yt-dlp ytsearch)
yt-dlp --dump-json "ytsearch5:query"
```

### Bilibili (yt-dlp)

```bash
# Get video metadata
yt-dlp --dump-json "https://www.bilibili.com/video/BVxxx"

# Download subtitles
yt-dlp --write-sub --write-auto-sub --sub-lang "zh-Hans,zh,en" --convert-subs vtt --skip-download -o "/tmp/%(id)s" "URL"
```

### Reddit (JSON API)

```bash
# Read a subreddit
curl -s "https://www.reddit.com/r/python/hot.json?limit=10" -H "User-Agent: agent-reach/1.0"

# Read a post with comments
curl -s "https://www.reddit.com/r/python/comments/POST_ID.json" -H "User-Agent: agent-reach/1.0"

# Search
curl -s "https://www.reddit.com/search.json?q=query&limit=10" -H "User-Agent: agent-reach/1.0"
```

Note: On servers, Reddit may block your IP. Use proxy or search via Exa instead.

### 小红书 / XiaoHongShu (mcporter + xiaohongshu-mcp)

```bash
# Search notes
mcporter call 'xiaohongshu.search_feeds(keyword: "query")'

# Read a note
mcporter call 'xiaohongshu.get_feed_detail(feed_id: "xxx", xsec_token: "yyy")'

# Get comments
mcporter call 'xiaohongshu.get_feed_comments(feed_id: "xxx", xsec_token: "yyy")'

# Post a note
mcporter call 'xiaohongshu.create_image_feed(title: "标题", desc: "内容", image_paths: ["/path/to/img.jpg"])'
```

### 抖音 / Douyin (mcporter + douyin-mcp-server)

```bash
# 解析抖音视频信息（分享链接 → 标题、作者、无水印视频URL等）
mcporter call 'douyin.parse_douyin_video_info(share_link: "https://v.douyin.com/xxx/")'

# 获取无水印视频下载链接
mcporter call 'douyin.get_douyin_download_link(share_link: "https://v.douyin.com/xxx/")'

# AI 提取视频语音文案（需要配置硅基流动 API Key）
mcporter call 'douyin.extract_douyin_text(share_link: "https://v.douyin.com/xxx/")'
```

> 无需登录即可解析视频。支持抖音分享链接和直接链接。

### GitHub (gh CLI)

```bash
# Search repos
gh search repos "query" --sort stars --limit 10

# View a repo
gh repo view owner/repo

# Search code
gh search code "query" --language python

# List issues
gh issue list -R owner/repo --state open

# View a specific issue/PR
gh issue view 123 -R owner/repo
```

### Web — Any URL (Jina Reader)

```bash
# Read any webpage as markdown
curl -s "https://r.jina.ai/URL" -H "Accept: text/markdown"

# Search the web
curl -s "https://s.jina.ai/query" -H "Accept: text/markdown"
```

### Exa Search (mcporter + exa MCP)

```bash
# Web search
mcporter call 'exa.web_search_exa(query: "query", numResults: 5)'

# Code search (GitHub, StackOverflow, docs)
mcporter call 'exa.get_code_context_exa(query: "how to parse JSON in Python", tokensNum: 3000)'

# Company research
mcporter call 'exa.company_research_exa(companyName: "OpenAI")'
```

### LinkedIn (mcporter + linkedin-scraper-mcp)

```bash
# View a profile
mcporter call 'linkedin.get_person_profile(linkedin_url: "https://linkedin.com/in/username")'

# Search people
mcporter call 'linkedin.search_people(keyword: "AI engineer", limit: 10)'

# View company
mcporter call 'linkedin.get_company_profile(linkedin_url: "https://linkedin.com/company/xxx")'
```

Fallback: `curl -s "https://r.jina.ai/https://linkedin.com/in/username"`

### Boss直聘 (mcporter + mcp-bosszp)

```bash
# Browse recommended jobs
mcporter call 'bosszhipin.get_recommend_jobs_tool(page: 1)'

# Search jobs
mcporter call 'bosszhipin.search_jobs_tool(keyword: "Python", city: "北京", page: 1)'

# View job details
mcporter call 'bosszhipin.get_job_detail_tool(job_url: "https://www.zhipin.com/job_detail/xxx")'
```

Fallback: `curl -s "https://r.jina.ai/https://www.zhipin.com/job_detail/xxx"`

### RSS (feedparser)

```python
python3 -c "
import feedparser
d = feedparser.parse('https://example.com/feed')
for e in d.entries[:5]:
    print(f'{e.title} — {e.link}')
"
```

## Troubleshooting

### Twitter "fetch failed"

bird CLI uses Node.js native `fetch()`, which doesn't respect `HTTP_PROXY`. Solutions:
1. Ensure `undici` is installed: `npm install -g undici`
2. Configure proxy: `agent-reach configure proxy http://user:pass@ip:port`
3. If still failing, use transparent proxy (Clash TUN, Proxifier)

### Channel broken?

Run `agent-reach doctor` — it shows what's wrong and how to fix it.
