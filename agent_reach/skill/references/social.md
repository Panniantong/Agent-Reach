# Social Media and Communities

XiaoHongShu, Twitter/X, Bilibili, V2EX, Reddit, Facebook, and Instagram.

## XiaoHongShu (multi-backend)

XiaoHongShu has multiple backends. **Run `agent-reach doctor --json` first and check `xiaohongshu.active_backend`**, then use the matching command group.

### Backend A: OpenCLI (preferred on desktop)

```bash
# Search notes
opencli xiaohongshu search "query" -f yaml

# Read note body + engagement data
# Use the complete URL returned by search, including xsec_token.
opencli xiaohongshu note "NOTE_URL" -f yaml

# Comments, including nested replies
opencli xiaohongshu comments NOTE_ID -f yaml

# Home recommendation feed
opencli xiaohongshu feed -f yaml

# Public notes from a user profile
opencli xiaohongshu user USER_ID -f yaml
```

Chrome must be open with the OpenCLI extension installed. OpenCLI may use only an existing Chrome session explicitly controlled by the user. Agent Reach must not log the user in or read browser cookies. `agent-reach configure xhs-cookies` does not inject cookies into OpenCLI.

If no existing browser session is available, do not automate login. Use backend B/C with a manual Cookie-Editor export.

### Backend B: xiaohongshu-mcp (server-oriented)

```bash
# Ask the user to export cookies manually with Cookie-Editor, then import explicitly
agent-reach configure xhs-cookies

# Read-only login/status check
mcporter call xiaohongshu.check_login_status --timeout 120000

# Search
mcporter call xiaohongshu.search_feeds keyword="query" --timeout 120000

# Note details + comments
mcporter call xiaohongshu.get_feed_detail feed_id="..." xsec_token="..." --timeout 120000
```

The first call may download a large headless-browser package, so use `--timeout 120000`. Authentication must use a manual Cookie-Editor export. The import accepts only the `xiaohongshu.com` cookie set supplied by the user; unrelated domains are ignored.

### Backend C: xhs-cli (legacy fallback)

```bash
xhs search "query"
xhs read NOTE_ID_OR_URL
xhs comments NOTE_ID_OR_URL
xhs hot
xhs feed
```

The upstream tool has been inactive since 2026-03 and some commands such as `xhs user`, `xhs user-posts`, and `xhs favorites` may fail. New installations should prefer OpenCLI or xiaohongshu-mcp.

### XiaoHongShu rules

- **Authentication boundary:** Agent Reach must not perform XiaoHongShu login or read browser cookies automatically.
- **xsec_token:** a bare note ID is often insufficient. Search/feed first and reuse the returned complete URL/ID plus token.
- **Rate control:** high-frequency searches and deep comment pagination can trigger verification. Space requests out.
- **Write actions:** prefer read-only use. Legacy write commands may fail because of upstream signature changes.

## Twitter/X (twitter-cli)

### Authentication

Cookies saved with `agent-reach configure twitter-cookies` are used by Doctor only to verify that explicit credentials exist. Doctor does not run upstream `twitter status` and does not set the current shell.

Before running `twitter` commands, explicitly provide:

```bash
export TWITTER_AUTH_TOKEN="..."
export TWITTER_CT0="..."
```

### Stable commands

```bash
# Home timeline
twitter feed -n 20

# Read one post and replies
twitter tweet URL_OR_ID

# Read an X Article
twitter article URL_OR_ID

# User timeline
twitter user-posts @username -n 20

# User profile
twitter user @username
```

### Commands that may be less stable

```bash
# Search can break when Twitter changes GraphQL endpoints
twitter search "query" -n 10

# Likes are platform-restricted
twitter likes
```

### Search retry chain

Stop as soon as one path returns usable content:

1. Retry once: `twitter search "query" -n 10`
2. Upgrade then retry: `pipx upgrade twitter-cli && twitter search "query" -n 10`
3. On desktop, use the OpenCLI fallback: `opencli twitter search "query" -f yaml`
4. If search still fails, use stable commands such as `twitter feed` or `twitter user-posts @username`.

### Twitter notes

- Install with `pipx install twitter-cli` and keep it current.
- Use a manual Cookie-Editor export; do not depend on automatic browser-cookie extraction.
- Avoid high-frequency use from VPS/data-center IPs, especially relationship/follower endpoints.
- If OpenCLI is installed on desktop, it can provide browser-session-backed Twitter search/article/timeline commands.
- Prefer structured YAML/JSON output for agent workflows.

## Bilibili

> **Do not use yt-dlp for Bilibili.** Tested Bilibili anti-bot controls return HTTP 412 for yt-dlp. Use bili-cli or OpenCLI.

```bash
# Search / hot / video details through bili-cli
bili search "query" --type video -n 5
bili hot -n 10
bili video BVxxx

# Subtitles through OpenCLI
opencli bilibili subtitle BVxxx
```

See [video.md](video.md) for audio transcription and API fallbacks.

## V2EX (public API)

No authentication is required.

### Hot topics

```bash
curl -s "https://www.v2ex.com/api/topics/hot.json" -H "User-Agent: agent-reach/1.0"
```

### Topics in a node

```bash
curl -s "https://www.v2ex.com/api/topics/show.json?node_name=python&page=1" -H "User-Agent: agent-reach/1.0"
```

### Topic details and replies

```bash
curl -s "https://www.v2ex.com/api/topics/show.json?id=TOPIC_ID" -H "User-Agent: agent-reach/1.0"
curl -s "https://www.v2ex.com/api/replies/show.json?topic_id=TOPIC_ID&page=1" -H "User-Agent: agent-reach/1.0"
```

### User information

```bash
curl -s "https://www.v2ex.com/api/members/show.json?username=USERNAME" -H "User-Agent: agent-reach/1.0"
```

### Python example

```python
from agent_reach.channels.v2ex import V2EXChannel

ch = V2EXChannel()

topics = ch.get_hot_topics(limit=10)
for topic in topics:
    print(f"[{topic['node_title']}] {topic['title']} ({topic['replies']} replies)")

node_topics = ch.get_node_topics("python", limit=5)

topic = ch.get_topic(1234567)
print(topic["title"], "—", topic["author"])

user = ch.get_user("Livid")
```

Node list: https://www.v2ex.com/planes

## Reddit (multi-backend, login required)

Reddit has **no zero-config path**. Anonymous JSON endpoints are blocked and the official API requires approval. Run `agent-reach doctor --json` and use `reddit.active_backend`.

### Backend A: OpenCLI (preferred on desktop)

```bash
# Search
opencli reddit search "query" -f yaml

# Read post + comments
opencli reddit read POST_ID -f yaml

# Browse subreddit / hot / popular
opencli reddit subreddit LocalLLaMA -f yaml
opencli reddit hot -f yaml
opencli reddit popular -f yaml

# Subreddit metadata
opencli reddit subreddit-info LocalLLaMA -f yaml
```

Chrome must be open and already logged in to reddit.com.

### Backend B: rdt-cli (legacy/server fallback)

```bash
rdt search "query" --limit 10
rdt read POST_ID
rdt sub python --limit 20
rdt popular --limit 10
rdt all --limit 10
```

Install the pinned GitHub version described by Agent Reach and run `rdt login` before search/read. On a server without a browser, follow Doctor's instructions for manual cookie configuration.

### Official API / PRAW

Only use this for users who already have approved Reddit API credentials. Do not recommend new users create a script app as the default path.

## Facebook (OpenCLI, login required)

Run `agent-reach doctor --json` first. The normal active backend is OpenCLI.

```bash
# Search users/pages/posts
opencli facebook search "query" -f yaml

# Profile/page information
opencli facebook profile zuck -f yaml

# Current account's News Feed
opencli facebook feed --limit 10 -f yaml

# Groups visible to the current account
opencli facebook groups --limit 20 -f yaml
```

Chrome must be open with the OpenCLI extension and already logged in to facebook.com. The groups command covers groups/recent activity visible to the current account; it does not promise arbitrary group-post/comment APIs.

## Instagram (OpenCLI, login required)

Run `agent-reach doctor --json` first. The normal active backend is OpenCLI.

```bash
# User search (not global post-keyword search)
opencli instagram search "query" -f yaml

# User profile
opencli instagram profile nasa -f yaml

# Recent posts from a user
opencli instagram user nasa --limit 12 -f yaml

# Explore
opencli instagram explore --limit 20 -f yaml

# Saved items for the current account
opencli instagram saved --limit 20 -f yaml
```

Chrome must be open with the OpenCLI extension and logged in to instagram.com. If the adapter returns 429 or login-required errors, have the user log in again in Chrome and reduce request frequency.
