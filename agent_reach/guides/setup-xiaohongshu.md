# XiaoHongShu Setup Guide

## Overview
Read and search XiaoHongShu notes. Implemented via [xhs-cli](https://github.com/jackwener/xiaohongshu-cli) (⭐1.5K, one-line install with pipx).

## Prerequisites
- Python 3.10+ (installed via pipx)
- A browser already logged in to xiaohongshu.com (used to export cookies)

## Steps the Agent Can Complete Automatically

### 1. Install xhs-cli
```bash
pipx install xiaohongshu-cli
```

### 2. Log in (extract cookies from the browser)
```bash
xhs login
```

> This automatically extracts cookies from your browser. If automatic extraction fails, you can import them manually (see below).

### 3. Verify
```bash
agent-reach doctor
```

You should see XiaoHongShu shown as ✅.

## Steps the User Must Do Manually

If `xhs login` fails to extract cookies automatically, you need to import the cookies manually:

> **Recommended method: Cookie-Editor browser export (most reliable)**
>
> 1. Install the [Cookie-Editor](https://chromewebstore.google.com/detail/cookie-editor/hlkenndednhfkekhgcdicdfddnkalmdm) extension in Chrome
> 2. Log in to xiaohongshu.com in your browser
> 3. Click the Cookie-Editor icon → Export → Header String
> 4. Send the exported string to the Agent and run: `agent-reach configure xhs-cookies "the exported cookie string"`
>
> **Note**: Do not rely on QR code login; the Cookie-Editor export method is the simplest and most reliable.

## Usage Examples

Search notes:
```bash
xhs search "keyword"
```

Read note details:
```bash
xhs read NOTE_ID
```

View comments:
```bash
xhs comments NOTE_ID
```

## FAQ

**Q: My cookies expired?**
A: Re-run `xhs login` or re-export via Cookie-Editor.

**Q: XiaoHongShu warns about IP risk?**
A: A residential proxy is recommended: `export HTTP_PROXY="http://user:pass@ip:port"`.

**Q: xhs-cli does not support my system?**
A: Make sure Python 3.10+ and pipx are installed. Then just run `pipx install xiaohongshu-cli`.

## Alternative: Docker MCP

If you are already using the [xiaohongshu-mcp](https://github.com/xpzouying/xiaohongshu-mcp) Docker solution, it also works fine:

```bash
docker run -d \
  --name xiaohongshu-mcp \
  -p 18060:18060 \
  xpzouying/xiaohongshu-mcp

mcporter config add xiaohongshu http://localhost:18060/mcp
```

xhs-cli is the currently recommended solution; it does not require Docker and is simpler to install.
