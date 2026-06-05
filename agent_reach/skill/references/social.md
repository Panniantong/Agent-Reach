# Social Media & Communities

XiaoHongShu, Douyin, Twitter/X, Weibo, Bilibili, V2EX, Reddit.

## XiaoHongShu (xhs-cli)

### Reliably working commands

```bash
# Search notes (recommended entry point)
xhs search "query"

# Read note details (must use a URL or ID from search results, not a bare note_id)
xhs read NOTE_ID_OR_URL

# View comments
xhs comments NOTE_ID_OR_URL

# Browse hot notes
xhs hot

# Recommended feed
xhs feed
```

### Known unstable commands (v0.6.4)

```bash
# The following commands may currently return an API error; use with caution:
xhs user USER_ID          # may return {code: -1}
xhs user-posts USER_ID    # may return {code: -1}
xhs favorites              # may return an API error
```

### Important notes

> **Install**: `pipx install xiaohongshu-cli`, then `xhs login` (automatically extracts the Cookie from the browser).
>
> **xsec_token restriction**: XiaoHongShu enforces an xsec_token mechanism, so **you cannot read with a bare note_id directly**. The correct flow is: first run `xhs search` or `xhs feed` to get results, then use the URL/ID from those results with `xhs read`. Manually constructing a note_id will be blocked.
>
> **Rate limiting**: High-frequency requests (bulk searches, deep comment paging) will trigger CAPTCHA. This is a platform limit that cannot be bypassed. It is recommended to wait 2-3 seconds between operations.
>
> **POST operation risk**: Write operations such as posting, commenting, and liking may return 406 on v0.6.x due to signature issues. If you need them, consider downgrading to v0.3.5 (`pipx install xiaohongshu-cli==0.3.5`).

## Douyin / Douyin

### Installation and configuration

`douyin-mcp-server` is an MCP server in **stdio mode**; it must be installed first and then registered with mcporter:

```bash
# 1. Install
pipx install douyin-mcp-server

# 2. Find the install path
pipx runpip douyin-mcp-server show -f 2>/dev/null | grep "Location" \
  || find ~/.local -name "douyin-mcp-server" 2>/dev/null | head -1

# 3. Register with mcporter (use stdio mode; replace the path with the output from the previous step)
mcporter config add douyin --command "/path/to/douyin-mcp-server" --scope home
```

> **Note**: `agent-reach install --channels douyin` does not yet support the Douyin channel (Douyin is in the "optional channels to be unlocked" list).
> HTTP mode (`mcporter config add douyin http://localhost:18070/mcp`) **does not work properly**; please use the stdio method above.

### Usage

```bash
# Parse video info
mcporter call 'douyin.parse_douyin_video_info(share_link: "https://v.douyin.com/xxx/")'

# Get a watermark-free download link
mcporter call 'douyin.get_douyin_download_link(share_link: "https://v.douyin.com/xxx/")'

# Extract the video transcript
mcporter call 'douyin.extract_douyin_text(share_link: "https://v.douyin.com/xxx/")'
```

> **No login required**

## Twitter/X (twitter-cli)

### Stable commands

```bash
# Home timeline (most stable)
twitter feed -n 20

# Read a single tweet (with replies)
twitter tweet URL_OR_ID

# Read a long post / X Article
twitter article URL_OR_ID

# User timeline
twitter user-posts @username -n 20

# User profile
twitter user @username
```

### Potentially unstable commands

```bash
# Search tweets (Twitter frequently changes GraphQL endpoints, may return 404)
twitter search "query" -n 10
# If search returns 404, upgrade twitter-cli: pipx upgrade twitter-cli

# likes (after 2024 you can only view your own, a platform limitation)
twitter likes
```

### Important notes

> **Install**: `pipx install twitter-cli` (make sure it is v0.8.5+)
>
> **Authentication**: It is recommended to export with Cookie-Editor and set the environment variables `TWITTER_AUTH_TOKEN` + `TWITTER_CT0`. Automatic extraction does not work in SSH/Docker/headless environments.
>
> **IP anti-abuse**: Do not call frequently from VPS/data-center IPs, especially followers/following, as there is a risk of account suspension. Use a residential proxy or a local environment.
>
> **search may fail**: Twitter frequently changes its GraphQL API, so the search command may return 404 at any time. If this happens, first run `pipx upgrade twitter-cli`. If the latest version still does not work, it means upstream has not yet caught up with Twitter's changes; use `twitter feed` instead.
>
> **Output format**: It is recommended to use `--yaml` or `--json` for structured output, which is friendlier for AI agents.

## Weibo

```bash
# Read with Jina Reader
curl -s "https://r.jina.ai/https://weibo.com/USER_ID/POST_ID"
```

> Weibo is mainly accessed through web scraping; the generic web reading approach is recommended.

## Bilibili

```bash
# Get video metadata
yt-dlp --dump-json "https://www.bilibili.com/video/BVxxx"

# Download subtitles
yt-dlp --write-sub --write-auto-sub --sub-lang "zh-Hans,zh,en" --convert-subs vtt --skip-download -o "/tmp/%(id)s" "URL"
```

> **Note**: Server IPs may hit a 412 error. Use `--cookies-from-browser chrome` or configure a proxy.

## V2EX (public API)

No authentication required; call the public API directly.

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
# topic_id is from the URL, e.g. https://www.v2ex.com/t/1234567
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

### Python usage example

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

# Browse a subreddit
rdt sub python --limit 20

# Browse popular
rdt popular --limit 10

# Browse /r/all
rdt all --limit 10
```

> **Install**: `pipx install rdt-cli` (make sure it is v0.4.2+). No login required to search and read.
> Features that require login: `rdt feed --subs-only` (subscription list), `rdt saved` (saved items).
> Using `--yaml` output is recommended, as it is friendlier for AI agents.
