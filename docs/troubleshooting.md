# Troubleshooting common problems

## Xueqiu: API returns 400

**Symptoms:** `agent-reach doctor` displays Xueqiu ⚠️, reporting `HTTP Error 400`

**Reason:** Xueqiu API requires a login cookie, which cannot be obtained through anonymous access.

**Solution:** Log in to xueqiu.com in Chrome, and then run:

```bash
agent-reach configure --from-browser chrome --platform xueqiu
```

Run `agent-reach doctor` again to confirm recovery ✅. Just run it again after the cookie expires.

---

## Boss Zhipin: `boss status` reports logged in, but search returns `AUTH_EXPIRED`

**Symptoms:** `boss status` / `status --live` returns `logged_in: true` (even with username),
But `boss ... search` immediately reports `{"code": "AUTH_EXPIRED", "message": "User is not logged in"}`.
Private Chrome may be stuck on a URL with `_security_check` at the same time, looking like an anti-crawl slider.

**Reason:** Boss has two login status stores, and the authentication channels are different:

| Storage | Who is using it |
|---|---|
| `~/.boss-agent/auth/session.enc` | `boss status` / `status --live`; low-risk operation of httpx channel (`detail` / `cities` / `job_card_httpx`). CDP search will also read it (if it cannot be read, it will directly report "not logged in"), but its cookie will never actually take effect when reusing the real Chrome context |
| Browser cookies in `~/.boss-chrome-profile` | Credentials actually carried by high-risk operations such as search/greet in `existing-browser` strict CDP mode |

`boss status` only verifies local session.enc. There are old credentials from a few days ago stored locally, and Chrome
When the profile itself is not logged in, it still reports `logged_in: true` - this is not proof that the login status is valid.
At the same time, the `_security_check` page is an anti-crawling challenge, and it will appear even if you are logged in. You cannot use it to determine the login status;
The superimposition of the two can easily misjudge "browser not logged in" as "stuck in the slider".

> Do not delete either storage. Missing session.enc will cause CDP searches to fail before connecting to the browser;
> Run `login --cdp` when you need to refresh it, don't delete files manually.

**Judgment order:**

1. `AUTH_EXPIRED` is the ground truth - when it appears, the browser is not logged in, no matter what `boss status` says;
2. `agent-reach doctor` checks the browser for a `wt2` cookie; use that result;
3. `boss status` is for reference only; the page URL is not used as a criterion at all.

**Solution:** Confirm visually in the dedicated Chrome window and log in to zhipin.com manually, and then synchronize the login status:

```bash
boss --cdp-url http://localhost:9222 login --cdp
agent-reach doctor    # The Boss message should report a browser login cookie (wt2)
```

> The first step after launching dedicated Chrome is always to ask the user to visually confirm the login status. Do not use `boss status` instead.

---

## Twitter/X: twitter-cli connection failed

**Symptoms:** `twitter search` or other commands return errors

**Reason:** twitter-cli requires `TWITTER_AUTH_TOKEN` and `TWITTER_CT0`
Environment variables are required to access the Twitter API. `agent-reach configure twitter-cookies`
The saved value is only used by doctor to check whether the configuration is complete; doctor does not perform upstream authentication and will not set the current
Shell. If your network environment requires a proxy to access x.com, you also need to configure the proxy.

**Solution:**

### Option 1: Set environment variable proxy

```bash
export TWITTER_AUTH_TOKEN="..."
export TWITTER_CT0="..."
export HTTP_PROXY="http://user:pass@host:port"
export HTTPS_PROXY="http://user:pass@host:port"
twitter search "test" -n 1
```

### Option 2: Use the global proxy tool

Let the proxy tool take over all network traffic, so that twitter-cli requests will also go through the proxy:

```bash
# macOS — ClashX / Surge turn on"enhanced mode"
# Linux — proxychains or tun2socks
proxychains twitter search "test" -n 1
```

### Option 3: Instead of using twitter-cli, use Exa search instead

When twitter-cli is not available, you can directly use Exa to search Twitter content:

```bash
mcporter call exa.web_search_exa query="site:x.com search term" numResults=5
```

### Option 4: Check Authentication

```bash
twitter check
```

> If "Missing credentials" is returned, it needs to be set in the process environment where the command is run.
> `TWITTER_AUTH_TOKEN` and `TWITTER_CT0`.
>
> **Fallback:** If you have bird CLI (`npm install -g @steipete/bird`) installed, it will also work fine. Agent Reach automatically detects installed tools.
