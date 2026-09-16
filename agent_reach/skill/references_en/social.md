# Social media and communities

XiaoHongShu, Twitter/X, Bilibili, V2EX, Reddit, Facebook, Instagram.

## XiaoHongShu (multi-backend)

XiaoHongShu has three backends. **Run `agent-reach doctor --json` first to see which `active_backend` xiaohongshu is on**, then use the matching command group.

### Backend A: OpenCLI (preferred on desktop)

```bash
# Search notes
opencli xiaohongshu search "query" -f yaml

# Read a note's body and engagement data (use the full URL from the search results, including xsec_token)
opencli xiaohongshu note "NOTE_URL" -f yaml

# Comments (nested replies supported)
opencli xiaohongshu comments NOTE_ID -f yaml

# Home recommendation feed
opencli xiaohongshu feed -f yaml

# A user's public notes
opencli xiaohongshu user USER_ID -f yaml
```

> Requires Chrome open with the OpenCLI extension installed. OpenCLI only uses a Chrome session the
> user already has and explicitly controls. Agent Reach does not log in on the user's behalf and does
> not read browser cookies. `agent-reach configure xhs-cookies` does not inject cookies into OpenCLI.
> If there is no existing session, do not log in automatically. Switch to backend B or C and configure
> it through the matching manual Cookie-Editor export flow.

### Backend B: xiaohongshu-mcp (server scenarios)

```bash
# Before authenticating, have the user export manually with Cookie-Editor, then import explicitly
agent-reach configure xhs-cookies

# Read-only status check
mcporter call xiaohongshu.check_login_status --timeout 120000

# Search
mcporter call xiaohongshu.search_feeds keyword="query" --timeout 120000

# Note detail plus comments (take feed_id and xsec_token from the search results)
mcporter call xiaohongshu.get_feed_detail feed_id="..." xsec_token="..." --timeout 120000
```

> The first call downloads roughly 150MB of headless browser, so always pass `--timeout 120000`.
> Authentication goes only through a manual Cookie-Editor export. After importing, run `check_login_status` first.
> That explicit command saves and imports the same-origin xiaohongshu.com cookie set the user provided, and the user
> should confirm its scope. Cookies from domains other than xiaohongshu.com are ignored.

### Backend C: xhs-cli (legacy alternative, upstream stopped updating in March 2026)

```bash
xhs search "query"          # Search
xhs read NOTE_ID_OR_URL     # Read a note (must use the URL/ID from search results, never a bare note_id)
xhs comments NOTE_ID_OR_URL # Comments
xhs hot                     # Trending
xhs feed                    # Recommendations
```

> Known to be unstable: `xhs user` / `xhs user-posts` / `xhs favorites` can return API errors (upstream is unmaintained). New users should go straight to backend A or B.

### General notes

> **Authentication boundary**: Agent Reach must not perform a XiaoHongShu login on the user's behalf and must not
> read browser cookies. OpenCLI may only use a Chrome session the user already has and explicitly controls.
> xiaohongshu-mcp and the legacy tools use a manual Cookie-Editor export.
>
> **xsec_token constraint**: XiaoHongShu enforces an xsec_token mechanism, so **a bare note_id cannot be read directly**. The correct flow is to search or pull the feed first, then read using the full URL/ID from those results. This applies to all three backends.
>
> **Rate control**: high-frequency requests (bulk searches, deep comment paging) trigger a captcha. This platform limit cannot be worked around. Leave 2 to 3 seconds between operations.
>
> **Write operations (posting, commenting, liking)**: read-only is recommended. xhs-cli v0.6.x write operations can return 406 because of signature problems.

## Twitter/X (twitter-cli)

### Authentication prerequisites

The cookie saved by `agent-reach configure twitter-cookies` through hidden input is only used by
`agent-reach doctor` to check whether the explicit credentials are complete. `doctor` does not run
upstream's `twitter status`, and it does not set up your current shell. Before running any `twitter`
command below, you must explicitly provide these in the same shell or subprocess environment:

```bash
export TWITTER_AUTH_TOKEN="..."
export TWITTER_CT0="..."
```

### Stable commands

```bash
# Home timeline (most stable)
twitter feed -n 20

# Read a single tweet (with replies)
twitter tweet URL_OR_ID

# Read a long-form post / X Article
twitter article URL_OR_ID

# A user's timeline
twitter user-posts @username -n 20

# A user's profile
twitter user @username
```

### Commands that may be unstable

```bash
# Tweet search (Twitter changes GraphQL endpoints often, so this can 404)
twitter search "query" -n 10

# likes (since 2024 you can only see your own, a platform limit)
twitter likes
```

### Retry chain when search fails (run in order, stop on success)

1. Simply retry once (intermittent failures are common): `twitter search "query" -n 10`
2. Upgrade and retry: `pipx upgrade twitter-cli && twitter search "query" -n 10`
3. Switch to the OpenCLI alternative (desktop, reuses the browser session): `opencli twitter search "query" -f yaml`
4. If none of that works, route around it with stable commands such as `twitter feed` or `twitter user-posts @somebody`

### Important notes

> **Install**: `pipx install twitter-cli` (make sure it is v0.8.5+)
>
> **Auth**: use a manual Cookie-Editor export only, then set the environment variables
> `TWITTER_AUTH_TOKEN` and `TWITTER_CT0` explicitly. Do not rely on automatic browser reading.
>
> **IP risk controls**: do not call frequently from a VPS or datacentre IP, especially followers/following, as it risks a ban. Use a residential proxy or a local environment.
>
> **OpenCLI alternative**: if OpenCLI is installed on the desktop, the full set `opencli twitter search/article/user-posts -f yaml` is available (browser session, no cookie environment variables needed).
>
> **Output format**: prefer `--yaml` or `--json` for structured output, which is friendlier for an AI agent.

## Bilibili

> ⚠️ **Do not use yt-dlp for Bilibili** (anti-abuse blocks it with 412 across the board, no known workaround). Use bili-cli or OpenCLI.

```bash
# Search / trending / video details (bili-cli, read-only, no login needed)
bili search "query" --type video -n 5
bili hot -n 10
bili video BVxxx

# Subtitles (OpenCLI, needs desktop Chrome)
opencli bilibili subtitle BVxxx
```

> For the detailed commands (audio transcription, direct API fallback) see [references/video.md](video.md).

## V2EX (public API)

No authentication needed, call the public API directly.

### Hot topics

```bash
curl -s "https://www.v2ex.com/api/topics/hot.json" -H "User-Agent: agent-reach/1.0"
```

### Node topics

```bash
# node_name examples: python, tech, jobs, qna, programmers
curl -s "https://www.v2ex.com/api/topics/show.json?node_name=python&page=1" -H "User-Agent: agent-reach/1.0"
```

### Topic detail

```bash
# topic_id comes from the URL, e.g. https://www.v2ex.com/t/1234567
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
    print(f"[{t['node_title']}] {t['title']} ({t['replies']} 回复)")

# Get topics from a node
node_topics = ch.get_node_topics("python", limit=5)

# Get topic detail plus replies
topic = ch.get_topic(1234567)
print(topic["title"], "—", topic["author"])

# Get user info
user = ch.get_user("Livid")
```

> **Node list**: https://www.v2ex.com/planes

## Reddit (multi-backend, session required)

**Reddit has no zero-config path**: the anonymous `.json` endpoints are blocked (403), and official API access has been effectively unobtainable through manual review since November 2025. Both backends rely on a logged-in session, so run `agent-reach doctor --json` first to see reddit's `active_backend`. Access from mainland China needs a proxy.

### Backend A: OpenCLI (preferred on desktop, reuses the browser session)

```bash
# Search posts
opencli reddit search "query" -f yaml

# Read a full post plus comments
opencli reddit read POST_ID -f yaml

# Browse a subreddit / hot / popular
opencli reddit subreddit LocalLLaMA -f yaml
opencli reddit hot -f yaml
opencli reddit popular -f yaml

# Subreddit metadata (subscriber count, description)
opencli reddit subreddit-info LocalLLaMA -f yaml
```

> Requires Chrome open and logged into reddit.com in the browser.

### Backend B: rdt-cli (legacy / server alternative, upstream stopped updating in March 2026)

```bash
rdt search "query" --limit 10   # Search posts
rdt read POST_ID                # Read a full post plus comments
rdt sub python --limit 20       # Browse a subreddit
rdt popular --limit 10          # Browse popular
rdt all --limit 10              # Browse /r/all
```

> **Install**: `pipx install 'git+https://github.com/public-clis/rdt-cli.git'` (the PyPI version lags, so install v0.4.2+ from GitHub). Run `rdt login` before searching and reading (on a server with no browser, write the cookie manually as the doctor output describes).
> Prefer `--yaml` output, which is friendlier for an AI agent.

### Advanced option: official API plus PRAW (only for users who already have credentials)

Users who registered a Reddit script app before November 2025 (holding a client_id/client_secret) can use PRAW against the official API (100 QPM free). New applications need manual review and personal projects are essentially never approved, so **do not recommend this path to new users**.

## Facebook (OpenCLI, session required)

Facebook goes through OpenCLI, reusing the facebook.com session in the user's Chrome. Run `agent-reach doctor --json` first to check facebook's `active_backend`, which should read `OpenCLI`. Do not recommend Jina, Exa or the Graph API as the default path.

```bash
# Search users / pages / posts
opencli facebook search "query" -f yaml

# User or page info
opencli facebook profile zuck -f yaml

# The current account's news feed
opencli facebook feed --limit 10 -f yaml

# Groups visible to the current account, and recent activity
opencli facebook groups --limit 20 -f yaml
```

> Requires Chrome open with the OpenCLI extension installed and logged into facebook.com. Facebook Groups currently only promises the group list and recent activity visible to the current account. It does not promise an API for arbitrary group posts and comments.

## Instagram (OpenCLI, session required)

Instagram goes through OpenCLI, reusing the instagram.com session in the user's Chrome. Run `agent-reach doctor --json` first to check instagram's `active_backend`, which should read `OpenCLI`. Do not fall back to instaloader by default, as it has historically been unstable with cookies, 401s and 429s.

```bash
# Search users (not a site-wide keyword search over posts)
opencli instagram search "query" -f yaml

# User profile
opencli instagram profile nasa -f yaml

# A user's recent posts
opencli instagram user nasa --limit 12 -f yaml

# Explore / Discover
opencli instagram explore --limit 20 -f yaml

# The current account's saved posts
opencli instagram saved --limit 20 -f yaml
```

> Requires Chrome open with the OpenCLI extension installed and logged into instagram.com. `instagram search` searches users, so to read posts you must first establish a username, then use `instagram user USERNAME`. If you hit 429 or login required, ask the user to log in again in Chrome and reduce the request rate.
