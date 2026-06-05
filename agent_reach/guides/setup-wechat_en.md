# WeChat Articles Setup Guide

## Overview
Read WeChat Official Account articles. Needs Playwright to handle WeChat's anti-bot measures.

## Agent Can Auto-Configure

1. Check Playwright availability:
   ```bash
   python3 -c "import playwright; print('ok')" 2>/dev/null
   ```

2. Install Playwright + browser:
   ```bash
   pip install playwright
   playwright install chromium
   ```

3. Test:
   ```bash
   curl -s "https://r.jina.ai/https://mp.weixin.qq.com/s/test-link" -H "Accept: text/markdown"
   ```

## User Action Required

Tell the user:
> WeChat article setup is straightforward — just need to install a browser component (~150MB).
> I'll handle the installation for you. It takes about 1-2 minutes.
> Once installed, I can read WeChat articles without any login.

## Agent Workflow

1. Install Playwright: `pip install playwright`
2. Install Chromium: `playwright install chromium`
3. Test by reading a WeChat article
4. Report: "✅ WeChat articles are configured! Send me any article link to read."
5. If install fails: "❌ Browser component install failed. May need ~150MB free space."
