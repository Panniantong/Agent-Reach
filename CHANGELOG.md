# Changelog

All notable changes to this project will be documented in this file.

---

## [Unreleased]

### Bug Fixes

#### Boss Zhipin — browser login-state misclassification

- **Root cause:** Boss Zhipin maintains two different authentication stores: local `~/.boss-agent/auth/session.enc` and browser cookies in the dedicated Chrome profile. `boss status` / `status --live` validate only the local store, while strict `existing-browser` CDP search actually uses browser cookies. An old local credential plus a logged-out browser could therefore produce `logged_in: true` and then fail search with `AUTH_EXPIRED`.
- **Fix:** `check()` now includes a fourth read-only probe, `_cdp_zhipin_login_cookie()`, using a minimal standard-library WebSocket client to query `Storage.getCookies` from the CDP browser. The browser's `wt2` cookie is treated as the browser-login signal without launching a browser or performing a search.
- **Runbook correction:** Doctor's browser-cookie probe is authoritative for the CDP browser. After launching dedicated Chrome, the user must visually confirm login. `AUTH_EXPIRED` is treated as ground truth and routes directly to the login flow; a `_security_check` page is handled separately as an anti-bot challenge.

### Features

#### Boss Zhipin channel

- Added the `boss` channel for job search and full JD retrieval through boss-agent-cli + a real Chrome session over CDP.
- `check()` performs four read-only layers: boss-agent-cli installed → port 9222 reachable → Zhipin tab present → browser `wt2` login cookie present.
- Retrieval uses the public API: `search_jobs` + `job_card_browser` + `browser_source="existing-browser"`.
- `agent-reach install --system --channels=boss` installs the backend pinned to an upstream commit after PRs #403–#407 were merged.
- Skill and installation docs support guided Boss Zhipin setup: the agent launches a dedicated loopback-only Chrome profile, the user logs in manually, and the agent verifies login/CDP afterward.
- Pinned dependency moved from fork snapshot `8ff6bd3` to upstream commit `4c991b7`.
- Code 37 is classified by the upstream message: environment risk becomes `ENVIRONMENT_RISK` and stops immediately; only explicit token/stoken expiry permits one refresh attempt. The dedicated Chrome profile should be reused long-term and requests should be rate-limited.

## [1.3.1] - 2026-03-27

### Bug Fixes

#### Xueqiu — comprehensive fixes

- **Fixed HTTP 400 root cause:** `_ensure_cookies()` could obtain only `acw_tc` from the homepage; `xq_a_token` is generated dynamically by Xueqiu's frontend JavaScript. Added a three-stage cookie loading strategy: config file saved by `--from-browser` → local Chrome extraction when explicitly used → homepage fallback.
- **Fixed User-Agent:** replaced `agent-reach/1.0`, which Xueqiu rejected, with a realistic Chrome UA.
- **Added missing Referer:** API requests now include `Referer: https://xueqiu.com/`.
- **Fixed `get_hot_posts()` endpoint:** replaced deprecated `/statuses/hot/listV3.json` with `/v4/statuses/public_timeline_by_category.json` and parse the `item.data` JSON payload for author/likes/text.
- **Fixed `urllib.request.quote` → `urllib.parse.quote`.**
- **Fixed `configure --from-browser` Xueqiu import:** added Xueqiu to `PLATFORM_SPECS` and save only when `xq_a_token` is present.
- **Corrected documentation:** Xueqiu is documented as requiring a browser cookie instead of “no configuration/public API.”
- **Improved errors:** `check()` points to `configure --from-browser chrome` instead of suggesting a generic proxy issue.

---

## [1.3.0] - 2026-03-12

### New Channels

#### V2EX

- Hot topics, node topics, topic details + replies, and user profiles through the public JSON API.
- Zero configuration — no authentication, proxy, or API key required.
- Added `get_hot_topics(limit)`, `get_node_topics(node_name, limit)`, `get_topic(id)`, and `get_user(username)`.

### Improvements

- Channel count: 14 → 15.

---

## [1.1.0] - 2025-02-25

### New Channels

#### ~~Instagram~~ (removed — upstream blocked)

- ~~Read public posts and profiles through [instaloader](https://github.com/instaloader/instaloader).~~
- **Removed:** Instagram anti-scraping changes broke the available open-source route. See [instaloader#2585](https://github.com/instaloader/instaloader/issues/2585). The channel can return when a reliable upstream route is available.

#### LinkedIn

- Read person profiles, company pages, and job details through [linkedin-scraper-mcp](https://github.com/stickerdaniel/linkedin-mcp-server).
- Search people and jobs through MCP, with Exa fallback.
- Fall back to Jina Reader when MCP is not configured.

#### Boss Zhipin

- QR-code login through [mcp-bosszp](https://github.com/mucsbr/mcp-bosszp).
- Job search and recruiter greeting through MCP.
- Jina Reader fallback for public job pages.

### Improvements

- Channel count: 9 → 12.
- `agent-reach doctor` detects all channels.
- Added `search-linkedin` and `search-bosszhipin` CLI subcommands.
- Updated the installation guide for the new channels.

---

## [1.0.0] - 2025-02-24

### Initial Release

- 9 channels: Web, Twitter/X, YouTube, Bilibili, GitHub, Reddit, XiaoHongShu, RSS, and Exa Search.
- CLI with `read`, `search`, `doctor`, and `install` commands.
- Unified channel interface with one pluggable Python module per platform.
- Automatic local/server environment detection.
- Built-in diagnostics through `agent-reach doctor`.
- Skill registration for Claude Code, OpenClaw, and Cursor.
