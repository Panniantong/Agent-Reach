# Changelog

All notable changes to this project will be documented in this file.

---

## [1.3.1] - 2026-03-27

### 🐛 Bug Fixes

#### 📈 Xueqiu — Comprehensive fix

- **Fixed the root cause of the 400 error:** `_ensure_cookies()` only visited the homepage, which can only obtain `acw_tc` (an anti-DDoS token). `xq_a_token` is generated dynamically by Xueqiu's frontend JS and cannot be obtained through a pure HTTP request. Added a three-tier cookie loading strategy: (1) read from the config file (saved via `--from-browser`) → (2) automatically extract from the local Chrome browser (requires browser-cookie3) → (3) homepage fallback
- **Fixed the User-Agent:** `"agent-reach/1.0"` was detected and rejected by Xueqiu's anti-scraping system; changed to a real Chrome UA
- **Fixed the missing `Referer` header:** all API requests now include `Referer: https://xueqiu.com/`
- **Fixed the `get_hot_posts()` endpoint:** the original endpoint `/statuses/hot/listV3.json` is deprecated (returns an empty body); switched to `/v4/statuses/public_timeline_by_category.json` and correctly parse the `item.data` JSON string to extract author/likes/text
- **Fixed `urllib.request.quote` → `urllib.parse.quote`:** explicitly use the correct module
- **Fixed `configure --from-browser` not extracting Xueqiu cookies:** added Xueqiu to `PLATFORM_SPECS`, saving only when `xq_a_token` is detected
- **Corrected misleading documentation:** "no configuration required"/"public API, no login required" in README/SKILL.md → now accurately describes that a browser cookie is needed
- **Improved error messages:** when `check()` fails it now suggests `configure --from-browser chrome` instead of "a proxy may be needed"

---

## [1.3.0] - 2026-03-12

### 🆕 New Channels

#### 💻 V2EX
- Hot topics, node topics, topic detail + replies, user profile via public JSON API
- Zero config — no auth, no proxy, no API key required
- `get_hot_topics(limit)`, `get_node_topics(node_name, limit)`, `get_topic(id)`, `get_user(username)`

### 📈 Improvements

- Channel count: 14 → 15

---

## [1.1.0] - 2025-02-25

### 🆕 New Channels

#### ~~📷 Instagram~~ (removed — upstream blocked)
- ~~Read public posts and profiles via [instaloader](https://github.com/instaloader/instaloader)~~
- **Removed:** Instagram's aggressive anti-scraping measures broke all available open-source tools (instaloader, etc.). See [instaloader#2585](https://github.com/instaloader/instaloader/issues/2585). Will re-add when upstream recovers.

#### 💼 LinkedIn
- Read person profiles, company pages, and job details via [linkedin-scraper-mcp](https://github.com/stickerdaniel/linkedin-mcp-server)
- Search people and jobs via MCP, with Exa fallback
- Fallback to Jina Reader when MCP is not configured

#### 🏢 Boss Zhipin
- QR code login via [mcp-bosszp](https://github.com/mucsbr/mcp-bosszp)
- Job search and recruiter greeting via MCP
- Fallback to Jina Reader for reading job pages

### 📈 Improvements

- Channel count: 9 → 12
- `agent-reach doctor` now detects all 12 channels
- CLI: added `search-linkedin`, `search-bosszhipin` subcommands
- Updated install guide with setup instructions for new channels

---

## [1.0.0] - 2025-02-24

### 🎉 Initial Release

- 9 channels: Web, Twitter/X, YouTube, Bilibili, GitHub, Reddit, XiaoHongShu, RSS, Exa Search
- CLI with `read`, `search`, `doctor`, `install` commands
- Unified channel interface — each platform is a single pluggable Python file
- Auto-detection of local vs server environments
- Built-in diagnostics via `agent-reach doctor`
- Skill registration for Claude Code / OpenClaw / Cursor
