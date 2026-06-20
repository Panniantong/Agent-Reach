# Twitter Advanced Features Setup Guide (twitter-cli)

Basic Twitter reading is available for free through Jina Reader, no configuration required.

Advanced features require twitter-cli (@public-clis/twitter-cli):

- Search tweets (`twitter search`)
- Read full tweets and conversation threads (`twitter tweet`, `twitter thread`)
- User timelines (`twitter timeline`)
- Long-form reading (`twitter article`)

twitter-cli is a free open-source tool (install via pipx), but requires your Twitter account cookies.

## Quick Setup

1. Check if twitter-cli is installed:

```bash
which twitter && echo "installed" || echo "not installed"
```

2. Install twitter-cli:

```bash
pipx install twitter-cli
```

3. Test if it's configured:

```bash
twitter search "test" -n 1
```

## Get Cookies (Cookie-Editor Method, Recommended)

1. Install [Cookie-Editor](https://cookie-editor.com/) browser extension
2. Log into x.com
3. Click Cookie-Editor icon → Export → Copy all
4. Run configuration command:

```bash
agent-reach configure twitter-cookies "paste cookie JSON here"
```

This automatically extracts `auth_token` and `ct0`, and writes them to environment variables.

## Manual Cookie Setup

If you already know your `auth_token` and `ct0`:

1. Install twitter-cli (if not installed): `pipx install twitter-cli`

2. Set environment variables:

```bash
export AUTH_TOKEN="your_auth_token"
export CT0="your_ct0"
```

3. Test:

```bash
twitter search "test" -n 1
```

## Proxy Configuration

> twitter-cli supports setting proxy via environment variables:

```bash
export HTTP_PROXY="http://user:pass@host:port"
export HTTPS_PROXY="http://user:pass@host:port"
twitter search "test" -n 1
```

You can also use global proxy tools:

```bash
proxychains twitter search "test" -n 1
```

## Fallback: bird CLI

If you have [bird CLI](https://www.npmjs.com/package/@steipete/bird) installed (`npm install -g @steipete/bird`), it will also work. Agent Reach automatically detects and uses installed bird. Both have similar functionality; twitter-cli is the currently recommended option.
