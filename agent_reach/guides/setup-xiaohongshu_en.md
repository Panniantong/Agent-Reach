# XiaoHongShu Setup Guide

## Overview
Read and search XiaoHongShu notes. Uses [xhs-cli](https://github.com/jackwener/xiaohongshu-cli) (⭐1.5K, one-line pipx install).

## Prerequisites
- Python 3.10+ (pipx installed)
- Browser logged into xiaohongshu.com (for cookie export)

## Agent Can Auto-Configure

### 1. Install xhs-cli
```bash
pipx install xiaohongshu-cli
```

### 2. Login (extract cookies from browser)
```bash
xhs login
```
> This auto-extracts cookies from your browser. If auto-extract fails, manual import is needed (see below).

### 3. Verify
```bash
agent-reach doctor
```
XiaoHongShu should show as ✅.

## User Action Required

If `xhs login` auto-extract fails, import cookies manually:

> **Cookie-Editor method (most reliable):**
> 1. Install [Cookie-Editor](https://chromewebstore.google.com/detail/cookie-editor/hlkenndednhfkekhgcdicdfddnkalmdm) extension in Chrome
> 2. Log into xiaohongshu.com in your browser
> 3. Click Cookie-Editor → Export → Header String
> 4. Send the exported string to your agent: `agent-reach configure xhs-cookies "the cookie string"`
>
> **Note**: Don't rely on QR code login — Cookie-Editor export is the simplest and most reliable method.

## Usage Examples

Search notes:
```bash
xhs search "query"
```

Read note details:
```bash
xhs read NOTE_ID_OR_URL
```

View comments:
```bash
xhs comments NOTE_ID_OR_URL
```

## Troubleshooting

**Q: Cookies expired?**
A: Re-run `xhs login` or re-export via Cookie-Editor.

**Q: IP risk warning?**
A: Use a residential proxy: `export HTTP_PROXY="http://user:pass@ip:port"`.

**Q: xhs-cli not working on my system?**
A: Make sure Python 3.10+ and pipx are installed. Run `pipx install xiaohongshu-cli`.
