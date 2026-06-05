# Social Media & Communities

XiaoHongShu, Douyin, Twitter/X, Weibo, Bilibili, V2EX, Reddit.

## XiaoHongShu (xhs-cli)

### Stable commands

```bash
# Search notes (recommended entry point)
xhs search "query"

# Read note details (must use URL/ID from search results, not bare note_id)
xhs read NOTE_ID_OR_URL

# View comments
xhs comments NOTE_ID_OR_URL

# Browse trending
xhs hot

# Recommended feed
xhs feed
```

### Known unstable commands (v0.6.4)

```bash
# These may return API errors, use with caution:
xhs user USER_ID          # may return {code: -1}
xhs user-posts USER_ID    # may return {code: -1}
xhs favorites              # may return API error
```

### Important notes

> **Install**: `pipx install xiaohongshu-cli`, then `xhs login` (auto-extracts cookies from browser).
>
> **xsec_token restriction**: XiaoHongShu enforces xsec_token. **Cannot read with bare note_id**. Correct flow: first `xhs search` or `xhs feed` to get results, then use the URL/ID from results for `xhs read`. Constructing a note_id directly will be blocked.
>
> **Rate limiting**: High frequency requests (batch search, deep comment scrolling) will trigger CAPTCHA — this is a platform limit that cannot be bypassed. Wait 2-3 seconds between operations.
>
> **POST operation risks**: Write operations (post, comment, like) in v0.6.x may return 406 due to signing issues. If needed, downgrade to v0.3.5 (`pipx install xiaohongshu-cli==0.3.5`).

## Douyin

### Installation & Configuration

`douyin-mcp-server` is a **stdio mode** MCP server. Install first, then register with mcporter:

```bash
# 1. Install
pipx install douyin-mcp-server

# 2. Find install path
pipx runpip douyin-mcp-server show -f 2>/dev/null | grep "Location" \
  || find ~/.local -name "douyin-mcp-server" 2>/dev/null | head -1

# 3. Register with mcporter (stdio mode, replace path with above output)
mcporter config add douyin --command "/path/to/douyin-mcp-server" --scope home
```

> **Note**: `agent-reach install --channels douyin` does not support the Douyin channel yet.
> HTTP mode (`mcporter config add douyin http://localhost:18070/mcp`) **does not work** — use the stdio method above.

### Usage

```bash
# Parse video info
mcporter call 'douyin.parse_douyin_video_info(share_link: "https://v.douyin.com/xxx/")'

# Get watermark-free download link
mcporter call 'douyin.get_douyin_download_link(share_link: "https://v.douyin.com/xxx/")'

# Extract video text
mcporter call 'douyin.extract_douyin_text(share_link: "https://v.douyin.com/xxx/")'
```

> **No login required**

## Twitter/X (twitter-cli)

### Stable commands

```bash
# Home timeline (most stable)
twitter feed -n 20

# Read single tweet (with replies)
twitter tweet URL_OR_ID

# Read long-form / X Article
twitter article URL_OR_ID

# User timeline
twitter user-posts @username -n 20

# User profile
twitter user @username
```

### Potentially unstable commands

```bash
# Search tweets (Twitter frequently changes GraphQL endpoints, may 404)
twitter search "query" -n 10
# If search returns 404, upgrade twitter-cli: pipx upgrade twitter-cli

# likes (after 2024 can only see your own — platform limitation)
twitter likes
```

### Important notes

> **Install**: `pipx install twitter-cli` (v0.8.5+)
>
> **Auth**: Use Cookie-Editor to export then set env vars `TWITTER_AUTH_TOKEN` + `TWITTER_CT0`. Auto-extract does not work in SSH/Docker/headless environments.
>
> **IP risk**: Do not make frequent calls from VPS/datacenter IPs, especially followers/following — risk of account suspension. Use residential proxy or local environment.
>
> **search may break**: Twitter frequently changes their GraphQL API. The search command may return 404 at any time. If so, first `pipx upgrade twitter-cli`. If the latest version still doesn't work, the upstream hasn't caught up yet — use `twitter feed` instead.
>
> **Output format**: Use `--yaml` or `--json` for structured output, better for AI agents.

## Weibo

```bash
# Read via Jina Reader
curl -s "https://r.jina.ai/https://weibo.com/USER_ID/POST_ID"
```

> Weibo is primarily accessed via web scraping. Use the general web reading method.

## Bilibili

```bash
# Get video metadata
yt-dlp --dump-json "https://www.bilibili.com/video/BVxxx"

# Download subtitles
yt-dlp --write-sub --write-auto-sub --sub-lang "zh-Hans,zh,en" --convert-subs vtt --skip-download -o "/tmp/%(id)s" "URL"
```

> **Note**: Server IPs may encounter 412 errors. Use `--cookies-from-browser chrome` or configure a proxy.

## V2EX (Public API)

No authentication required — call the public API directly.

### Hot topics

```bash
curl -s "https://www.v2ex.com/api/topics/hot.json" -H "User-Agent: agent-reach/1.0"
```

### Node topics

```bash
# node_name examples: python, tech, jobs, qna, programmers
curl -s "https://www.v2ex.com/api/topics/show.json?node_name=python&page=1" -H "User-Agent: agent-reach/1.0"
```

### Topic details

```bash
# topic_id from URL, e.g. https://www.v2ex.com/t/1234567
curl -s "https://www.v2ex.com/api/topics/show.json?id=TOPIC_ID" -H "User-Agent: agent-reach/1.0"
```

### Topic replies

```bash
curl -s "https://www.v2ex.com/api/replies/show.json?topic_id=TOPIC_ID&page=1" -H "User-Agent: agent-reach/1.0"
```

### User info

```bash
curl -s "https://www.v2ex.com/api/members/show.json?username=USERNAME" -H "User-Agent: agent-reach/1.0"
```

### Python example

```python
from agent_reach.channels.v2ex import V2EXChannel

ch = V2EXChannel()

# Get hot topics
topics = ch.get_hot_topics(limit=10)
for t in topics:
    print(f"[{t['node_title']}] {t['title']} ({t['replies']} replies)")

# Get node topics
node_topics = ch.get_node_topics("python", limit=5)

# Get topic details + replies
topic = ch.get_topic(1234567)
print(topic["title"], "—", topic["author"])

# Get user info
user = ch.get_user("Livid")
```

> **Node list**: https://www.v2ex.com/planes

## Reddit (rdt-cli)

```bash
# Search posts
rdt search "query" --limit 10

# Read full post + comments
rdt read POST_ID

# Browse subreddit
rdt sub python --limit 20

# Browse popular
rdt popular --limit 10

# Browse /r/all
rdt all --limit 10
```

> **Install**: `pipx install rdt-cli` (v0.4.2+). No login required for search and reading.
> Login needed for: `rdt feed --subs-only` (subscriptions), `rdt saved` (bookmarks).
> Use `--yaml` output for AI agent friendliness.
