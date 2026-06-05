# Troubleshooting

## Xueqiu: API returns 400

**Symptom:** `agent-reach doctor` shows Xueqiu as ⚠️ with an `HTTP Error 400`.

**Cause:** The Xueqiu API requires a login cookie and cannot be accessed anonymously.

**Solution:** Log in to xueqiu.com in Chrome, then run:

```bash
agent-reach configure --from-browser chrome
```

Run `agent-reach doctor` again to confirm it returns to ✅. Once the cookie expires, just run the command again.

---

## Twitter/X: twitter-cli connection fails

**Symptom:** `twitter search` or other commands return an error.

**Cause:** twitter-cli needs the AUTH_TOKEN and CT0 environment variables to access the Twitter API. If your network requires a proxy to reach x.com, you need to configure one.

**Solution:**

### Option 1: Set a proxy via environment variables

```bash
export HTTP_PROXY="http://user:pass@host:port"
export HTTPS_PROXY="http://user:pass@host:port"
twitter search "test" -n 1
```

### Option 2: Use a global proxy tool

Let a proxy tool take over all network traffic so that twitter-cli's requests go through the proxy as well:

```bash
# macOS — enable "Enhanced Mode" in ClashX / Surge
# Linux — proxychains or tun2socks
proxychains twitter search "test" -n 1
```

### Option 3: Skip twitter-cli and use Exa search instead

When twitter-cli is unavailable, you can search Twitter content directly with Exa:

```bash
mcporter call 'exa.web_search_exa(query: "site:x.com search terms", numResults: 5)'
```

### Option 4: Check authentication

```bash
twitter check
```

> If it returns "Missing credentials", you need to set the AUTH_TOKEN and CT0 environment variables.
>
> **Fallback:** If you already have the bird CLI installed (`npm install -g @steipete/bird`), it works as well. Agent Reach automatically detects installed tools.
