# XiaoHongShu (Little Red Book) Setup Guide

## Features

Read and search XiaoHongShu posts. Implemented via [xhs-cli](https://github.com/jackwener/xiaohongshu-cli) (⭐1.5K, one-line pipx install).

## Prerequisites
- Python 3.10+ (for pipx installation)
- Browser logged into xiaohongshu.com (for cookie export)

## Steps Agent Can Complete Automatically

### 1. Install xhs-cli
```bash
pipx install xiaohongshu-cli
```

### 2. Login (extract cookies from browser)
```bash
xhs login
```

> This automatically extracts cookies from your browser. If automatic extraction fails, manually import (see below).

### 3. Verify
```bash
agent-reach doctor
```

You should see XiaoHongShu showing as ✅.

## Manual User Steps

If `xhs login` automatic extraction fails, manually import cookies:

> **Recommended: Cookie-Editor browser export (most reliable)**
>
> 1. Install [Cookie-Editor](https://chromewebstore.google.com/detail/cookie-editor/hlkenndednhfkekhgcdicdfddnkalmdm) extension in Chrome
> 2. Log into xiaohongshu.com in browser
> 3. Click Cookie-Editor icon → Export → Header String
> 4. Send the exported string to your Agent, run: `agent-reach configure xhs-cookies "exported cookie string"`
>
> **Note:** Don't rely on QR code login. Cookie-Editor export is the simplest and most reliable method.

## Usage Examples

Search posts:
```bash
xhs search "keyword"
```

Read post details:
```bash
xhs read NOTE_ID
```

View comments:
```bash
xhs comments NOTE_ID
```

## FAQ

**Q: Cookies expired?**
A: Re-run `xhs login` or re-export via Cookie-Editor.

**Q: XiaoHongShu shows IP risk warning?**
A: Recommended to use residential proxy: `export HTTP_PROXY="http://user:pass@ip:port"`.

**Q: xhs-cli doesn't support my system?**
A: Ensure Python 3.10+ and pipx are installed. Run `pipx install xiaohongshu-cli`.

## Alternative: Docker MCP

If you're already using the [xiaohongshu-mcp](https://github.com/xpzouying/xiaohongshu-mcp) Docker solution, it will also work:

```bash
docker run -d \
  --name xiaohongshu-mcp \
  -p 18060:18060 \
  xpzouying/xiaohongshu-mcp

mcporter config add xiaohongshu http://localhost:18060/mcp
```

xhs-cli is the currently recommended solution — no Docker needed, simpler installation.
