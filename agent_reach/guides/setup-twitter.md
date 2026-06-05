# Twitter Advanced Features Setup Guide (twitter-cli)

Basic Twitter reading is available for free via Jina Reader, with no configuration needed.

Advanced features require twitter-cli (@public-clis/twitter-cli):

- Search tweets (`twitter search`)
- Read full tweets and conversation threads (`twitter tweet`, `twitter thread`)
- User timelines (`twitter timeline`)
- Long-form article reading (`twitter article`)

twitter-cli is a free, open-source tool (installed via pipx), but it requires your Twitter account cookie.

## Quick Setup

1. Check whether twitter-cli is installed:

```bash
which twitter && echo "installed" || echo "not installed"
```

2. Install twitter-cli:

```bash
pipx install twitter-cli
```

3. Test whether it is configured:

```bash
twitter search "test" -n 1
```

## Getting the Cookie (Cookie-Editor method, recommended)

1. Install the [Cookie-Editor](https://cookie-editor.com/) browser extension
2. Log in to x.com
3. Click the Cookie-Editor icon → Export → copy all
4. Run the configuration command:

```bash
agent-reach configure twitter-cookies "pasted cookie JSON"
```

This automatically extracts `auth_token` and `ct0` and writes them to environment variables.

## Setting the Cookie Manually

If you already know your `auth_token` and `ct0`:

1. Install twitter-cli (if not already installed): `pipx install twitter-cli`

2. Set the environment variables:

```bash
export AUTH_TOKEN="your auth_token"
export CT0="your ct0"
```

3. Test:

```bash
twitter search "test" -n 1
```

## Proxy Configuration

> twitter-cli supports configuring a proxy via environment variables:

```bash
export HTTP_PROXY="http://user:pass@host:port"
export HTTPS_PROXY="http://user:pass@host:port"
twitter search "test" -n 1
```

You can also use a global proxy tool:

```bash
proxychains twitter search "test" -n 1
```

## Fallback: bird CLI

If you have already installed the [bird CLI](https://www.npmjs.com/package/@steipete/bird) (`npm install -g @steipete/bird`), it also works fine. Agent Reach automatically detects and uses an installed bird. The two are functionally similar; twitter-cli is the currently recommended solution.
