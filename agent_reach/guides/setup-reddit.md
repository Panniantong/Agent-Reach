# Reddit Setup Guide

## What it provides

Reddit blocks many non-browser anonymous access paths, and the anonymous JSON endpoints are not a reliable zero-config route. Agent Reach therefore uses authenticated backends.

Preferred order:

1. **OpenCLI on desktop** — reuses an existing Chrome session controlled by the user.
2. **rdt-cli** — legacy/server fallback using explicit login/cookie configuration.

Typical commands:

```bash
opencli reddit search "query" -f yaml
opencli reddit read POST_ID -f yaml

rdt search "query" --limit 10
rdt read POST_ID
```

## Steps the agent can perform

Check current backend status:

```bash
agent-reach doctor --json
```

If the user explicitly approves installing the Reddit channel:

```bash
agent-reach install --env=auto --system --channels=reddit
```

For the rdt-cli fallback, Agent Reach pins the GitHub source used by the codebase. Follow Doctor's installation message rather than installing an arbitrary version.

## User action required

A logged-in session is required.

- Desktop/OpenCLI: the user logs in to reddit.com in their own Chrome session.
- rdt-cli: use `rdt login` where browser extraction is appropriate, or follow Doctor's manual-cookie guidance on servers.

In networks where reddit.com is blocked, a user-approved proxy may also be required.

## Examples

```bash
opencli reddit search "python best practices" -f yaml
opencli reddit read POST_ID -f yaml

rdt search "python best practices" --limit 5
rdt read POST_ID
```

## Search-only fallback

If Exa is configured, it can search indexed Reddit pages without replacing the authenticated Reddit backend:

```bash
mcporter call exa.web_search_exa query="site:reddit.com python best practices" numResults=5
```
