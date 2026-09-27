# Twitter Advanced Function Configuration Guide (twitter-cli)

Twitter Basic Reading is available for free with Jina Reader and requires no configuration.

Advanced features require twitter-cli (@public-clis/twitter-cli):

- Search tweets (`twitter search`)
- Read the complete tweet and conversation chain (`twitter tweet`, `twitter thread`)
- User timeline (`twitter timeline`)
- Long article reading (`twitter article`)

twitter-cli is a free open source tool (pipx installation), but requires your Twitter account cookie.

## Quick configuration

1. Check whether twitter-cli is installed:

```bash
which twitter && echo "installed" || echo "not installed"
```

2. Install twitter-cli:

```bash
pipx install twitter-cli
```

3. Confirm that the command has been installed (no authentication request is made at this time):

```bash
twitter --help
```

## Get Cookie (Cookie-Editor method, recommended)

1. Install [Cookie-Editor](https://cookie-editor.com/) browser extension
2. Log in to x.com
3. Click the Cookie-Editor icon → Export → Header String
4. Run the configuration command:

```bash
agent-reach configure twitter-cookies
```

This will extract `auth_token` and `ct0` and save them safely to
`~/.agent-reach/config.yaml` for `agent-reach doctor` to check whether the explicit credentials are complete.
`doctor` will not execute `twitter status`, will not verify whether the account is available in real time, and will not modify the current shell.

By default, only `~/.agent-reach/config.yaml` is written. With explicit consent and
the `--sync-legacy-twitter` flag, credentials are also written to:

- `~/.config/xfetch/session.json`
- `~/.config/bird/credentials.env`

```bash
agent-reach configure twitter-cookies --sync-legacy-twitter
```

`agent-reach uninstall` reports these legacy copies and will not automatically delete
them. Remove them manually only after confirming they are no longer needed.

`twitter` is an independent upstream command and does not read Agent Reach configuration.
Before calling it directly, explicitly set `TWITTER_AUTH_TOKEN` and `TWITTER_CT0` in
the current shell or child-process environment. Do not rely on automatic browser-cookie reads.

## Manually set cookies

If you already know `auth_token` and `ct0`:

1. Install twitter-cli (if not installed): `pipx install twitter-cli`

2. Set environment variables:

```bash
export TWITTER_AUTH_TOKEN="your_auth_token"
export TWITTER_CT0="your_ct0"
```

3. Test:

```bash
twitter search "test" -n 1
```

## Proxy configuration

> twitter-cli supports setting proxy through environment variables:

```bash
export HTTP_PROXY="http://user:pass@host:port"
export HTTPS_PROXY="http://user:pass@host:port"
twitter search "test" -n 1
```

You can also use the global proxy tool:

```bash
proxychains twitter search "test" -n 1
```

## Fallback:bird CLI

An existing [bird CLI](https://www.npmjs.com/package/@steipete/bird) installation also works (`npm install -g @steipete/bird`). Agent Reach will automatically detect and use the installed bird. The functions of the two are similar, and twitter-cli is the current recommended solution.
