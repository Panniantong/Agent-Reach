# Twitter Advanced Setup Guide (twitter-cli)

Basic Twitter reading works via Jina Reader with no configuration.

Advanced features need twitter-cli (@public-clis/twitter-cli):
- Search tweets (`twitter search`)
- Read full tweets and threads (`twitter tweet`, `twitter thread`)
- User timelines (`twitter timeline`)
- Long-form articles (`twitter article`)

twitter-cli is free and open source (pipx installable), but needs your Twitter account cookie.

## Quick Config

1. Check if twitter-cli is installed:
   ```bash
   which twitter
   ```

2. Install twitter-cli:
   ```bash
   pipx install twitter-cli
   ```

3. Test:
   ```bash
   twitter feed -n 5
   ```

## Getting Cookies (Cookie-Editor, recommended)

1. Install [Cookie-Editor](https://cookie-editor.com/) browser extension
2. Log into x.com
3. Click Cookie-Editor icon → Export → copy all
4. Run the config command:
   ```bash
   agent-reach configure twitter-cookies "pasted cookie JSON"
   ```

This auto-extracts `auth_token` and `ct0`, and writes them to the config.

## Manual Cookie Setup

If you already know `auth_token` and `ct0`:

1. Install twitter-cli: `pipx install twitter-cli`
2. Set environment variables:
   ```bash
   export TWITTER_AUTH_TOKEN="your_auth_token"
   export TWITTER_CT0="your_ct0"
   ```
3. Test: `twitter feed -n 5`

## Proxy Configuration

twitter-cli supports proxies via environment variables:
```bash
export HTTP_PROXY="http://user:pass@ip:port"
export HTTPS_PROXY="http://user:pass@ip:port"
```
