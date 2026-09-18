# Financial Data

Xueqiu stock quotes, search, and popular market/community content. Quotes may be delayed and are not investment advice.

## Check status first

```bash
agent-reach doctor --json
```

If `xueqiu.active_backend` is populated, use that backend. A `null` value means Doctor did not complete live content verification; it does not prove that no backend exists. Xueqiu requires an authenticated session or a minimal cookie set, so HTTP 400 must not be interpreted as "stock not found."

## OpenCLI (preferred on desktop with an existing Chrome login)

```bash
# Verify current login
opencli xueqiu whoami -f yaml

# Stock search and quote
opencli xueqiu search "NVIDIA" -f yaml
opencli xueqiu stock NVDA -f yaml

# Popular content and stocks
opencli xueqiu hot -f yaml
opencli xueqiu hot-stock -f yaml

# Show all read-only commands
opencli xueqiu --help
```

OpenCLI may reuse only a browser session the user already controls. Do not automatically run `opencli xueqiu login`. If no session exists, have the user log in with Chrome or explicitly import the minimal Xueqiu cookie:

```bash
agent-reach configure --from-browser chrome --platform xueqiu
```

This stores only the required `xq_a_token`; it must not collect unrelated platform cookies.

## Validation and failure handling

- Success means a non-empty stock name/code/price or content list; exit code 0 with empty fields is not sufficient.
- HTTP 400 usually indicates a session/cookie problem rather than a missing stock symbol.
- If `whoami` works but `stock`/`hot` fails, report it as an adapter/parsing/platform-interface problem instead of misdiagnosing login state.
