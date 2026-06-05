# Troubleshooting Guide

## Xueqiu: API returns 400

**Symptom:** `agent-reach doctor` shows Xueqiu ⚠️, reporting `HTTP Error 400`

**Cause:** Xueqiu API requires login cookies that can't be obtained anonymously.

**Solution:** Login to xueqiu.com in Chrome, then run:
```bash
agent-reach configure --from-browser chrome
```

Re-run `agent-reach doctor` to confirm ✅. Reapply when cookies expire.

## Twitter/X: twitter-cli connection failed

**Symptom:** `twitter search` or other commands return errors

**Cause:** twitter-cli needs `AUTH_TOKEN` and `CT0` environment variables. If your network requires a proxy to access x.com, configure it.

**Solution:**

### Option 1: Set proxy environment variables
```bash
export HTTP_PROXY="http://127.0.0.1:7890"
export HTTPS_PROXY="http://127.0.0.1:7890"
```

### Option 2: Use a global proxy tool
Let the proxy tool handle all traffic:
- macOS — ClashX / Surge enable "enhanced mode"
- Linux — proxychains or tun2socks

### Option 3: Search via Exa instead of twitter-cli
```bash
mcporter call 'exa.web_search_exa(query: "site:x.com query", numResults: 5)'
```

## Reddit: 403 / connection issues

**Solution:** Use rdt-cli:

```bash
pipx install rdt-cli
rdt search "query" -n 10
```

Free, no proxy, no API key needed.

## Bilibili: 412 / server IP blocked

**Solution:** Configure a residential proxy:
```bash
agent-reach configure proxy http://user:pass@ip:port
```
Cheap option: https://www.webshare.io ($1/month)