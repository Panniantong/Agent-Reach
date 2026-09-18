# Twitter/X Advanced Setup Guide (twitter-cli)

Basic public-page reading may be possible through Jina Reader. Advanced Twitter/X operations use twitter-cli.

Supported examples include:

- Search: `twitter search`
- Read a post/thread: `twitter tweet`, `twitter thread`
- User timeline: `twitter user-posts` / supported timeline commands
- X Articles: `twitter article`

twitter-cli is open source but requires account cookies.

## Quick setup

1. Check whether twitter-cli is installed:

```bash
which twitter && echo "installed" || echo "not installed"
```

2. Install it if the user approved the optional channel:

```bash
pipx install twitter-cli
```

3. Verify only that the command is executable:

```bash
twitter --help
```

## Get cookies with Cookie-Editor

1. Install [Cookie-Editor](https://cookie-editor.com/).
2. Log in to x.com in the user's browser.
3. In Cookie-Editor choose **Export → Header String**.
4. Run:

```bash
agent-reach configure twitter-cookies
```

This extracts `auth_token` and `ct0` and saves them in `~/.agent-reach/config.yaml` so Doctor can verify that explicit credentials are present.

Doctor does **not** run `twitter status`, does not prove the account is currently accepted by Twitter, and does not modify the current shell.

By default, Agent Reach writes only its own configuration. It writes legacy copies only when the user explicitly requests synchronization:

```bash
agent-reach configure twitter-cookies --sync-legacy-twitter
```

That may additionally update:

- `~/.config/xfetch/session.json`
- `~/.config/bird/credentials.env`

`agent-reach uninstall` warns about these legacy copies but does not silently delete them.

## Run twitter-cli with explicit environment variables

The upstream `twitter` command does not read Agent Reach's config file. Set credentials in the current shell or child-process environment:

```bash
export TWITTER_AUTH_TOKEN="YOUR_AUTH_TOKEN"
export TWITTER_CT0="YOUR_CT0"
twitter search "test" -n 1
```

Do not depend on automatic browser-cookie extraction.

## Proxy configuration

If the user's network requires a proxy:

```bash
export HTTP_PROXY="http://user:pass@host:port"
export HTTPS_PROXY="http://user:pass@host:port"
twitter search "test" -n 1
```

Or use a user-approved system proxy tool:

```bash
proxychains twitter search "test" -n 1
```

## Fallback: bird CLI

If [bird CLI](https://www.npmjs.com/package/@steipete/bird) is already installed, Agent Reach can detect it as an additional fallback. twitter-cli remains the preferred CLI in this routing setup.
