# WeChat Official Account Setup Guide

## Overview
Read WeChat Official Account articles. Playwright is required to handle WeChat's anti-scraping mechanisms.

## Steps the Agent Can Complete Automatically

1. Check whether Playwright is installed:
```bash
python3 -c "import playwright; print('installed')" 2>&1
```

2. Install Playwright + browser:
```bash
pip install playwright
playwright install chromium
```

3. Test after installation completes:
```bash
curl -s "https://r.jina.ai/https://mp.weixin.qq.com/s/a-test-link" -H "Accept: text/markdown"
```

## Steps the User Must Do Manually

Tell the user:

> Setting up WeChat Official Account support is simple; it only requires installing a browser component (about 150MB).
>
> I'll handle the installation for you, you don't need to do anything. The installation takes about 1-2 minutes.
>
> Once installed, you can read WeChat Official Account articles directly, with no login required.

## Agent Workflow

1. Install Playwright: `pip install playwright`
2. Install Chromium: `playwright install chromium`
3. Test: read a WeChat article
4. Report back: "✅ WeChat Official Account is configured! Send me any Official Account article link and I can read it."
5. If the installation fails (insufficient space, etc.): "❌ The browser component failed to install. This may be due to insufficient disk space (about 150MB is required)."
