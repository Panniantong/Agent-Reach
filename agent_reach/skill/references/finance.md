# financial quotes

Xueqiu stock quotes, searches and popular content. Quotes may be delayed and do not constitute investment advice.

## Check the status first

```bash
agent-reach doctor --json
```

Use the backend named by `xueqiu.active_backend`. A value of `null` means Doctor
has not verified live content. Xueqiu requires a logged-in session or explicit
cookies; HTTP 400 does not mean a stock symbol is missing.

## OpenCLI (Priority is given when the desktop already has Chrome login status)

```bash
# Verify current login status
opencli xueqiu whoami -f yaml

# Stock search and real-time quotes
opencli xueqiu search "NVIDIA" -f yaml
opencli xueqiu stock NVDA -f yaml

# Popular content and popular stocks
opencli xueqiu hot -f yaml
opencli xueqiu hot-stock -f yaml

# View all read-only commands
opencli xueqiu --help
```

OpenCLI only reuses browser sessions that already exist and are explicitly controlled by the user. Don't automate
`opencli xueqiu login`; When there is no ready-made login state, let the user log in in Chrome first, or import it explicitly
Minimum cookies required for Xueqiu:

```bash
agent-reach configure --from-browser chrome --platform xueqiu
```

This configuration only reads and saves `xq_a_token` and does not collect cookies from other platforms.

## Acceptance and failure handling

- Returning a stock name, code, price, or a non-empty content list is considered successful; exit code 0 but an empty field is not considered successful.
- HTTP 400 is usually a session/cookie issue and does not mean the ticker does not exist.
- When `whoami` succeeds but `stock`/`hot` fails, report it according to the adapter resolution or platform interface problem, and do not misdiagnose it as not logged in.
