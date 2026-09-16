# Financial market data

Xueqiu stock quotes, search and trending content. Quotes may be delayed and are not investment advice.

## Check status first

```bash
agent-reach doctor --json
```

When `xueqiu.active_backend` has a value, use that backend. A value of `null` only means Doctor
did not complete live content verification. Xueqiu needs a logged-in session or a minimal cookie,
so never read an HTTP 400 as proof the stock does not exist.

## OpenCLI (preferred when the desktop Chrome session is already logged in)

```bash
# Verify the current session
opencli xueqiu whoami -f yaml

# Stock search and live quotes
opencli xueqiu search "英伟达" -f yaml
opencli xueqiu stock NVDA -f yaml

# Trending content and trending stocks
opencli xueqiu hot -f yaml
opencli xueqiu hot-stock -f yaml

# See all read-only commands
opencli xueqiu --help
```

OpenCLI only reuses a browser session the user already has and explicitly controls. Do not run
`opencli xueqiu login` automatically. When no session exists, ask the user to log in via Chrome
first, or explicitly import the minimal cookie Xueqiu needs:

```bash
agent-reach configure --from-browser chrome --platform xueqiu
```

That command reads and saves only `xq_a_token`. It does not collect cookies for any other platform.

## Acceptance and failure handling

- Success means a returned stock name, ticker, price, or a non-empty content list. Exit code 0 with empty fields is not success.
- HTTP 400 is usually a session or cookie problem, not a non-existent ticker.
- When `whoami` succeeds but `stock`/`hot` fails, report it as an adapter parsing or platform API problem. Do not misdiagnose it as being logged out.
