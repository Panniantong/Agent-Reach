# Troubleshooting Guide

## Xueqiu / Snowball: API returns 400

**Symptom:** `agent-reach doctor` shows Xueqiu with ⚠️, reporting `HTTP Error 400`

**Cause:** The Xueqiu API requires login cookies and cannot be accessed anonymously.

**Solution:** Log into xueqiu.com in Chrome, then run:

```bash
agent-reach configure --from-browser chrome
```

Run `agent-reach doctor` again to confirm ✅. Re-run this command when cookies expire.

---

## Twitter/X: twitter-cli connection failed

**Symptom:** `twitter search` or other commands return errors

**Cause:** twitter-cli requires AUTH_TOKEN and CT0 environment variables to access the Twitter API. If your network requires a proxy to reach x.com, you need to configure proxy settings.

**Solutions:**

### Option 1: Set environment variable proxy

```bash
export HTTP_PROXY="http://user:pass@host:port"
export HTTPS_PROXY="http://user:pass@host:port"
twitter search "test" -n 1
```

### Option 2: Use global proxy tools

Let your proxy tool handle all network traffic, so twitter-cli requests go through the proxy:

```bash
# macOS — ClashX / Surge enable "Enhanced Mode"
# Linux — proxychains or tun2socks
proxychains twitter search "test" -n 1
```

### Option 3: Replace twitter-cli with Exa search

When twitter-cli is unavailable, you can use Exa to search Twitter content:

```bash
mcporter call 'exa.web_search_exa(query: "site:x.com search_term", numResults: 5)'
```

### Option 4: Check authentication

```bash
twitter check
```

> If you see "Missing credentials", set AUTH_TOKEN and CT0 environment variables.
>
> **Fallback:** If you have bird CLI installed (`npm install -g @steipete/bird`), it will also work. Agent Reach automatically detects installed tools.
