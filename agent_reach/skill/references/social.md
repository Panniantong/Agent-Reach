# Social Media and Community

XiaoHongShu, Twitter/X, Bilibili, V2EX, Reddit, Facebook, Instagram.

## XiaoHongShu (multiple backends)

XiaoHongShu has three backends. First run `agent-reach doctor --json` to see which `active_backend` is XiaoHongShu’s, and then use the corresponding command group.

### Backend A: OpenCLI (desktop preferred)

```bash
# Search notes
opencli xiaohongshu search "query" -f yaml

# Read note content and engagement (use the full search-result URL, including xsec_token)
opencli xiaohongshu note "NOTE_URL" -f yaml

# Comment (includes nested replies)
opencli xiaohongshu comments NOTE_ID -f yaml

# Home page recommendation feed
opencli xiaohongshu feed -f yaml

# Public notes on user homepage
opencli xiaohongshu user USER_ID -f yaml
```

> Chrome must be open with the OpenCLI extension installed. OpenCLI only uses an
> existing and explicitly controlled Chrome session. Agent Reach does not log in
> for the user or read browser cookies.
> `agent-reach configure xhs-cookies` does not inject cookies into OpenCLI.
> If no session exists, do not automate login. Use backend B/C with a manual
> Cookie-Editor export as described below.

### Backend B: xiaohongshu-mcp (server scenario)

```bash
# Have the user export with Cookie-Editor, then explicitly import the cookies
agent-reach configure xhs-cookies

# Read only check current status
mcporter call xiaohongshu.check_login_status --timeout 120000

# search
mcporter call xiaohongshu.search_feeds keyword="query" --timeout 120000

# Note details+Comment (feed_id and xsec_token Take from search results)
mcporter call xiaohongshu.get_feed_detail feed_id="..." xsec_token="..." --timeout 120000
```

> The first call will automatically download about 150MB headless browser, be sure to bring `--timeout 120000`.
> Authentication only uses Cookie-Editor to manually export; run `check_login_status` first after importing.
> This explicit command will save/import the xiaohongshu.com same-domain cookie set provided by the user. The user should
> Confirm scope; non-xiaohongshu.com domain cookies will be ignored.

### Backend C: xhs-cli (legacy installations; upstream maintenance stopped in March 2026)

```bash
xhs search "query"          # search
xhs read NOTE_ID_OR_URL     # read notes (must be used in the search results URL/ID, Can't be naked note_id)
xhs comments NOTE_ID_OR_URL # Comment
xhs hot                     # Popular
xhs feed                    # recommend
```

> Known to be unstable: `xhs user` / `xhs user-posts` / `xhs favorites` may return an API error (upstream stops updating and no one fixes it). New users are advised to go directly to backend A/B.

### General Notes

> **Authentication Boundary**: Agent Reach must not perform XiaoHongShu login for the user, nor must it read the browser
> Cookies. OpenCLI can only use Chrome sessions that the user already has and explicitly controls;
> xiaohongshu-mcp / The legacy tool uses Cookie-Editor to manually export.
>
> **xsec_token restriction**: XiaoHongShu enforces the xsec_token mechanism, and **cannot directly use bare note_id to read**. Correct process: First search/feed to get the results, and then use the complete URL/ID in the results to read. All three backends are the same.
>
> **Frequency Control**: High-frequency requests (batch search, deep reading of comments) will trigger verification codes, and platform restrictions cannot be bypassed. The interval between each operation is 2-3 seconds.
>
> **Writing operations (post/comment/like)**: Read-only is recommended. xhs-cli v0.6.x write operations may return 406 due to signature issues.

## Twitter/X (twitter-cli)

### Authentication prerequisites

`agent-reach configure twitter-cookies` saves credentials through a hidden prompt.
`agent-reach doctor` only checks that those credentials are present; it does not
execute `twitter status` or configure the current shell. Before running the commands
below, explicitly set these variables in the shell or child-process environment:

```bash
export TWITTER_AUTH_TOKEN="..."
export TWITTER_CT0="..."
```

### Stable command

```bash
# Home Timeline (most stable)
twitter feed -n 20

# Read a single tweet (with reply)
twitter tweet URL_OR_ID

# Read long text / X Article
twitter article URL_OR_ID

# User timeline
twitter user-posts @username -n 20

# User profile
twitter user @username
```

### Potentially unstable commands

```bash
# Search tweets (Twitter Change frequently GraphQL endpoint, possible 404)
twitter search "query" -n 10

# Likes (since 2024, platform restrictions allow viewing only your own likes)
twitter likes
```

### Retry chain when search fails (execute in order, stop on success)

1. Try again directly (occasional failures are common): `twitter search "query" -n 10`
2. Try again after upgrading: `pipx upgrade twitter-cli && twitter search "query" -n 10`
3. Change to OpenCLI alternative (desktop, reuse browser login state): `opencli twitter search "query" -f yaml`
4. If all else fails, use stable commands such as `twitter feed` / `twitter user-posts @somebody` to bypass it.

### Important Notes

> **Installation**: `pipx install twitter-cli` (ensuring v0.8.5+)
>
> **Authentication**: Only use Cookie-Editor to export manually, and then explicitly set environment variables
> `TWITTER_AUTH_TOKEN` + `TWITTER_CT0`; don't rely on automatic browser reading.
>
> **IP Risk Control**: Do not make frequent calls on VPS/data center IP, especially followers/following, as there is a risk of account ban. Use a residential proxy or local environment.
>
> **OpenCLI alternative**: If OpenCLI is installed on the desktop, the full set of `opencli twitter search/article/user-posts -f yaml` is available (browser login state, no cookie environment variable required).
>
> **Output format**: It is recommended to use `--yaml` or `--json` to obtain structured output, which is more friendly to AI agents.

## Bilibili

> ⚠️ **Do not use yt-dlp to read Bilibili** (risk control has been fully blocked with 412, and there is no solution in the actual test). Use bili-cli/OpenCLI.

```bash
# search / Popular / Video details (bili-cli, Read only no login required)
bili search "query" --type video -n 5
bili hot -n 10
bili video BVxxx

# subtitle (OpenCLI, Desktop required Chrome)
opencli bilibili subtitle BVxxx
```

> For detailed commands (audio transcription, API direct connection), see [references/video.md](video.md).

## V2EX (Public API)

No authentication required, call the public API directly.

### Popular Topics

```bash
curl -s "https://www.v2ex.com/api/topics/hot.json" -H "User-Agent: agent-reach/1.0"
```

### Node topics

```bash
# node_name like: python, tech, jobs, qna, programmers
curl -s "https://www.v2ex.com/api/topics/show.json?node_name=python&page=1" -H "User-Agent: agent-reach/1.0"
```

### Topic details

```bash
# topic_id from URL get, like https://www.v2ex.com/t/1234567
curl -s "https://www.v2ex.com/api/topics/show.json?id=TOPIC_ID" -H "User-Agent: agent-reach/1.0"
```

### Topic reply

```bash
curl -s "https://www.v2ex.com/api/replies/show.json?topic_id=TOPIC_ID&page=1" -H "User-Agent: agent-reach/1.0"
```

### User information

```bash
curl -s "https://www.v2ex.com/api/members/show.json?username=USERNAME" -H "User-Agent: agent-reach/1.0"
```

### Python call example

```python
from agent_reach.channels.v2ex import V2EXChannel

ch = V2EXChannel()

# Get popular posts
topics = ch.get_hot_topics(limit=10)
for t in topics:
    print(f"[{t['node_title']}] {t['title']} ({t['replies']} reply)")

# Get node posts
node_topics = ch.get_node_topics("python", limit=5)

# Get post details + reply
topic = ch.get_topic(1234567)
print(topic["title"], "—", topic["author"])

# Get user information
user = ch.get_user("Livid")
```

> **Node List**: https://www.v2ex.com/planes

## Reddit (multiple backends, must be logged in)

**Reddit does not have a zero-configuration path**: The anonymous `.json` endpoint has been blocked (403), and the official API has basically not been approved manually since 2025-11. Both backends rely on the login state. First run `agent-reach doctor --json` to see reddit's `active_backend`. Access from mainland China requires a proxy.

### Backend A: OpenCLI (desktop preferred, reuse browser login state)

```bash
# Search posts
opencli reddit search "query" -f yaml

# Read full post + Comment
opencli reddit read POST_ID -f yaml

# Browse subreddit / Popular / Popular
opencli reddit subreddit LocalLLaMA -f yaml
opencli reddit hot -f yaml
opencli reddit popular -f yaml

# subreddit Meta information (Number of subscriptions, Introduction)
opencli reddit subreddit-info LocalLLaMA -f yaml
```

> Requires Chrome to be open and reddit.com logged into the browser.

### Backend B: rdt-cli (legacy/server alternative, upstream maintenance stopped in March 2026)

```bash
rdt search "query" --limit 10   # Search posts
rdt read POST_ID                # Read full post + Comment
rdt sub python --limit 20       # Browse subreddit
rdt popular --limit 10          # Browse popular
rdt all --limit 10              # Browse /r/all
```

> **Installation**: `pipx install 'git+https://github.com/public-clis/rdt-cli.git'` (the PyPI version is lagging behind, you need to install v0.4.2+ from GitHub). Run `rdt login` before searching or reading (manually write Cookie when the server does not have a browser, see doctor's tips).
> It is recommended to use `--yaml` output, which is more friendly to AI agents.

### Advanced options: Official API + PRAW (only for users with existing credentials)

Users who have registered the Reddit script app (with client_id/client_secret) before 2025-11 can use PRAW to use the official API (100 QPM free). New applications require manual approval and personal projects are basically not approved. **Do not recommend new users to take this path**.

## Facebook (OpenCLI, must be logged in)

Facebook uses OpenCLI to reuse the facebook.com login status in users’ Chrome. Run `agent-reach doctor --json` first to see `active_backend` on Facebook. Normally it should be `OpenCLI`. Do not recommend Jina/Exa/Graph API as the default path.

```bash
# Search users / Home page / Post
opencli facebook search "query" -f yaml

# User or Page information
opencli facebook profile zuck -f yaml

# Current account News Feed
opencli facebook feed --limit 10 -f yaml

# List of groups visible to the current account/Latest news
opencli facebook groups --limit 20 -f yaml
```

> Requires Chrome to be open with the OpenCLI extension installed, and logged in to facebook.com. Facebook Groups currently only commits to reading the group list/recent updates visible to the current account, and does not commit to any group post and comment API.

## Instagram (OpenCLI, must log in)

Instagram uses OpenCLI and reuses the user’s instagram.com login status in Chrome. Run `agent-reach doctor --json` first and see `active_backend` on instagram. Normally it should be `OpenCLI`. Don't restore instaloader by default; cookies/401/429 are historically unstable.

```bash
# Search users (Not a site-wide post keyword search)
opencli instagram search "query" -f yaml

# user Profile
opencli instagram profile nasa -f yaml

# User's recent posts
opencli instagram user nasa --limit 12 -f yaml

# Explore / Discover
opencli instagram explore --limit 20 -f yaml

# Current account collection
opencli instagram saved --limit 20 -f yaml
```

> Requires Chrome to be open with the OpenCLI extension installed and logged in to instagram.com. `instagram search` is a user search; to read the post, you need to determine the username first, and then use `instagram user USERNAME`. If 429 / login required appears, first ask the user to log in again in Chrome and reduce the frequency.
