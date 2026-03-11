---
name: agent-reach
description: >
  Give your AI agent eyes to see the entire internet. 7500+ GitHub stars.
  Search and read 14 platforms: Twitter/X, Reddit, YouTube, GitHub, Bilibili,
  XiaoHongShu (小红书), Douyin (抖音), Weibo (微博), WeChat Articles (微信公众号),
  LinkedIn, Instagram, RSS, Exa web search, and any web page.
  One command install, zero config for 8 channels, agent-reach doctor for diagnostics.
  Use when: (1) user asks to search or read any of these platforms,
  (2) user shares a URL from any supported platform,
  (3) user asks to search the web, find information online, or research a topic,
  (4) user asks to post, comment, or interact on supported platforms,
  (5) user asks to configure or set up a platform channel.
  Triggers: "搜推特", "搜小红书", "看视频", "搜一下", "上网搜", "帮我查", "全网搜索",
  "search twitter", "read tweet", "youtube transcript", "search reddit",
  "read this link", "看这个链接", "B站", "bilibili", "抖音视频",
  "微信文章", "公众号", "LinkedIn", "GitHub issue", "RSS", "微博",
  "search online", "web search", "find information", "research",
  "帮我配", "configure twitter", "configure proxy", "帮我安装".
metadata:
  openclaw:
    homepage: https://github.com/Panniantong/Agent-Reach
---

# Agent Reach — Usage Guide

Upstream tools for 13+ platforms. Call them directly.

Run `agent-reach doctor` to check which channels are available.

## ⚠️ Workspace Rules

**Never create files in the agent workspace.** Use `/tmp/` for temporary output and `~/.agent-reach/` for persistent data.

## Web — Any URL

```bash
curl -s "https://r.jina.ai/URL"
```

## Web Search (Exa)

```bash
mcporter call 'exa.web_search_exa(query: "query", numResults: 5)'
mcporter call 'exa.get_code_context_exa(query: "code question", tokensNum: 3000)'
```

## Twitter/X (xreach)

```bash
xreach search "query" -n 10 --json          # search
xreach tweet URL_OR_ID --json                # read tweet (supports /status/ and /article/ URLs)
xreach tweets @username -n 20 --json         # user timeline
xreach thread URL_OR_ID --json               # full thread
```

## YouTube (yt-dlp)

```bash
yt-dlp --dump-json "URL"                     # video metadata
yt-dlp --write-sub --write-auto-sub --sub-lang "zh-Hans,zh,en" --skip-download -o "/tmp/%(id)s" "URL"
                                             # download subtitles, then read the .vtt file
yt-dlp --dump-json "ytsearch5:query"         # search
```

## Bilibili (yt-dlp)

```bash
yt-dlp --dump-json "https://www.bilibili.com/video/BVxxx"
yt-dlp --write-sub --write-auto-sub --sub-lang "zh-Hans,zh,en" --convert-subs vtt --skip-download -o "/tmp/%(id)s" "URL"
```

> Server IPs may get 412. Use `--cookies-from-browser chrome` or configure proxy.

## Reddit

```bash
curl -s "https://www.reddit.com/r/SUBREDDIT/hot.json?limit=10" -H "User-Agent: agent-reach/1.0"
curl -s "https://www.reddit.com/search.json?q=QUERY&limit=10" -H "User-Agent: agent-reach/1.0"
```

> Server IPs may get 403. Search via Exa instead, or configure proxy.

## GitHub (gh CLI)

```bash
gh search repos "query" --sort stars --limit 10
gh repo view owner/repo
gh search code "query" --language python
gh issue list -R owner/repo --state open
gh issue view 123 -R owner/repo
```

## 小红书 / XiaoHongShu (mcporter)

```bash
mcporter call 'xiaohongshu.search_feeds(keyword: "query")'
mcporter call 'xiaohongshu.get_feed_detail(feed_id: "xxx", xsec_token: "yyy")'
mcporter call 'xiaohongshu.get_feed_detail(feed_id: "xxx", xsec_token: "yyy", load_all_comments: true)'
mcporter call 'xiaohongshu.publish_content(title: "标题", content: "正文", images: ["/path/img.jpg"], tags: ["tag"])'
```

> Requires login. Use Cookie-Editor to import cookies.

## 抖音 / Douyin

优先使用 Agent Reach 自带脚本：

```bash
python3 -m agent_reach.scripts.douyin_cli --link "https://v.douyin.com/xxx/" --action info
python3 -m agent_reach.scripts.douyin_cli --link "https://v.douyin.com/xxx/" --action download --output /tmp/agent-reach-douyin
python3 -m agent_reach.scripts.douyin_cli --link "https://v.douyin.com/xxx/" --action extract --output /tmp/agent-reach-douyin --save-video
```

### Recommended workflow

1. Run `--action info` first to confirm the link resolves and inspect `video_id`, title, and download URL.
2. Run `--action download` when the user wants the local video file only.
3. Run `--action extract` when the user wants transcript extraction; set `API_KEY` first.
4. Treat empty transcript as a soft failure, not a hard crash. The CLI returns a `warning` field when audio is present but no useful text is extracted.

### Input notes

- Accept either a clean Douyin URL or a full share text block copied from the app.
- The script extracts the first valid Douyin URL from the text automatically.
- Output defaults to `/tmp/agent-reach-douyin` unless the caller passes `--output`.

### Output notes

- `info` prints JSON with `video_id`, `title`, and direct video `url`.
- `download` prints JSON with `video_info` and `video_path`.
- `extract` prints JSON with `video_info`, `text`, `output_path`, and optional `warning`.
- Transcript output is saved under `<output>/<video_id>/transcript.md`.
- When `--save-video` is set, the downloaded `.mp4` is copied into the same video folder.

### Known limitations

- Search is not built in yet. Current Douyin support is link-first: parse, download, and extract after the user provides a share link.
- Transcript quality depends on the source audio and SiliconFlow recognition quality.
- Some videos may return an empty transcript even when the extraction flow succeeds.

See `docs/douyin-output.md` for output structure and `docs/douyin-validation.md` for real-world validation notes.

## 微信公众号 / WeChat Articles

**Search** (miku_ai):
```python
python3 -c "
import asyncio
from miku_ai import get_wexin_article
async def s():
    for a in await get_wexin_article('query', 5):
        print(f'{a[\"title\"]} | {a[\"url\"]}')
asyncio.run(s())
"
```

**Read** (Camoufox — bypasses WeChat anti-bot):
```bash
cd ~/.agent-reach/tools/wechat-article-for-ai && python3 main.py "https://mp.weixin.qq.com/s/ARTICLE_ID"
```

> WeChat articles cannot be read with Jina Reader or curl. Must use Camoufox.

## LinkedIn (mcporter)

```bash
mcporter call 'linkedin.get_person_profile(linkedin_url: "https://linkedin.com/in/username")'
mcporter call 'linkedin.search_people(keyword: "AI engineer", limit: 10)'
```

Fallback: `curl -s "https://r.jina.ai/https://linkedin.com/in/username"`

## RSS (feedparser)

## RSS

```python
python3 -c "
import feedparser
for e in feedparser.parse('FEED_URL').entries[:5]:
    print(f'{e.title} — {e.link}')
"
```

## Troubleshooting

- **Channel not working?** Run `agent-reach doctor` — shows status and fix instructions.
- **Twitter fetch failed?** Ensure `undici` is installed: `npm install -g undici`. Configure proxy: `agent-reach configure proxy URL`.

## Setting Up a Channel ("帮我配 XXX")

If a channel needs setup (cookies, Docker, etc.), fetch the install guide:
https://raw.githubusercontent.com/Mithranda/agent-reach-douyin/main/docs/install.md

User only provides cookies. Everything else is your job.
