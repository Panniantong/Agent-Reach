# Exa Search Setup Guide

## What it provides

Exa is an AI semantic search engine. Agent Reach connects to it through MCP. The current integration is free and does not require an API key.

After setup, you can use:

- General semantic web search
- Reddit discovery through queries such as `site:reddit.com`
- Twitter/X discovery through queries such as `site:x.com`

## Steps the agent can perform

After the user explicitly authorizes system changes, `agent-reach install --env=auto --system` can complete these steps. The default install command without `--system` performs read-only checks only.

### 1. Install mcporter

```bash
npm install -g mcporter
```

### 2. Register the Exa MCP endpoint

```bash
mcporter config add exa https://mcp.exa.ai/mcp --scope home
```

### 3. Verify

```bash
agent-reach doctor | grep "Search"
mcporter call exa.web_search_exa query="test" numResults=1
```

## User action required

None for authentication. The current Exa MCP endpoint does not require registration or an API key.

If `agent-reach install --system` could not configure Exa because of a network error, run the two setup commands above manually.

## FAQ

**Is there a search quota?**  
The MCP endpoint is operated by Exa. Availability, pricing, or limits may change upstream; Agent Reach should report current upstream behavior rather than assuming unlimited access.

**What is mcporter?**  
mcporter is a command-line bridge for calling MCP servers. Agent Reach uses it for integrations such as Exa and XiaoHongShu MCP backends.
