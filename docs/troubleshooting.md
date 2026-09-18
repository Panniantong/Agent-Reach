# Troubleshooting

## Xueqiu: API returns HTTP 400

**Symptom:** `agent-reach doctor` shows a warning for Xueqiu and reports `HTTP Error 400`.

**Cause:** Xueqiu's API requires a logged-in cookie and cannot be used anonymously.

**Fix:** Log in to xueqiu.com in Chrome, then run:

```bash
agent-reach configure --from-browser chrome --platform xueqiu
```

Run `agent-reach doctor` again to verify recovery. Repeat the import when the cookie expires.

---

## Boss Zhipin: `boss status` says logged in, but search returns `AUTH_EXPIRED`

**Symptom:** `boss status` / `status --live` returns `logged_in: true` (possibly with a username), but `boss ... search` immediately returns `{"code": "AUTH_EXPIRED", ...}`. The dedicated Chrome window may also be on a URL containing `_security_check`, which can look like an anti-bot challenge.

**Cause:** Boss Zhipin uses two separate authentication stores for different paths:

| Store | Used by |
|---|---|
| `~/.boss-agent/auth/session.enc` | `boss status` / `status --live`; low-risk httpx operations such as `detail`, `cities`, and `job_card_httpx`. CDP search also requires this store to exist before the browser connection is established, but its cookies are not the credentials actually used by an existing real Chrome context. |
| Browser cookies inside `~/.boss-chrome-profile` | The credentials actually used by high-risk operations such as search/greet when `existing-browser` strict-CDP mode reuses the real Chrome context. |

`boss status` validates only the local `session.enc`. If that file contains old credentials while the dedicated Chrome profile is logged out, it can still report `logged_in: true`. That is not proof that the browser session is authenticated.

A `_security_check` page is an anti-bot challenge and can appear even when the account is logged in, so the current page URL must not be used as the login-state signal.

> Do not delete either store. A missing `session.enc` can make CDP search fail before the browser connection is established. Refresh it with `login --cdp` instead of deleting files manually.

**Decision order:**

1. `AUTH_EXPIRED` from search is the ground truth: the browser is logged out regardless of `boss status`.
2. The Boss row in `agent-reach doctor` probes the browser's `wt2` cookie; use that as the browser-session signal.
3. Treat `boss status` as supporting information only. Never infer login state from the page URL.

**Fix:** In the dedicated Chrome window, have the user visually confirm the account is logged in. If necessary, the user logs in manually. Then synchronize the local credential store:

```bash
boss --cdp-url http://localhost:9222 login --cdp
agent-reach doctor
```

After starting the dedicated Chrome profile, the first step should always be a visual login check by the user; do not replace it with `boss status`.

---

## Twitter/X: twitter-cli cannot connect

**Symptom:** `twitter search` or another command returns an authentication/network error.

**Cause:** twitter-cli requires `TWITTER_AUTH_TOKEN` and `TWITTER_CT0` in the process environment. Values saved with `agent-reach configure twitter-cookies` are used by Agent Reach only to check whether explicit credentials exist; doctor does not run upstream authentication and does not modify the current shell. A proxy may also be required on networks that cannot reach x.com directly.

### Option 1: Explicit environment variables and proxy

```bash
export TWITTER_AUTH_TOKEN="..."
export TWITTER_CT0="..."
export HTTP_PROXY="http://user:pass@host:port"
export HTTPS_PROXY="http://user:pass@host:port"
twitter search "test" -n 1
```

### Option 2: System-wide proxy tool

If a local proxy tool handles all outbound traffic, twitter-cli can use that route as well:

```bash
# macOS: ClashX / Surge enhanced mode
# Linux: proxychains or tun2socks
proxychains twitter search "test" -n 1
```

### Option 3: Use Exa as a search fallback

If twitter-cli is unavailable, search indexed X/Twitter pages through Exa:

```bash
mcporter call exa.web_search_exa query="site:x.com search terms" numResults=5
```

### Option 4: Check credentials

```bash
twitter check
```

If it returns `Missing credentials`, set `TWITTER_AUTH_TOKEN` and `TWITTER_CT0` in the process environment.

> **Fallback:** if bird CLI is already installed (`npm install -g @steipete/bird`), Agent Reach can detect it as an additional fallback.
