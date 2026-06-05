# Exa Search Setup Guide

## Overview
Exa is an AI semantic search engine. It connects via MCP, **free and with no API key required**. Once configured, it unlocks:
- Web-wide semantic search
- Reddit search (via site:reddit.com)
- Twitter search (via site:x.com)

## Steps the Agent Can Complete Automatically

`agent-reach install --env=auto` performs the following steps automatically, so manual action is usually not needed.

### 1. Install mcporter
```bash
npm install -g mcporter
```

### 2. Register the Exa MCP
```bash
mcporter config add exa https://mcp.exa.ai/mcp
```

### 3. Verify
```bash
agent-reach doctor | grep "Search"
mcporter call 'exa.web_search_exa(query: "test", numResults: 1)'
```

## Steps the User Must Do Manually

**None.** Exa connects via MCP, is free, and requires no registration and no API key.

If `agent-reach install` did not configure Exa automatically due to a network issue, just run the two commands above manually.

## FAQ

**Q: Is there a search request limit?**
A: The MCP endpoint is provided officially by Exa (mcp.exa.ai) and is currently free and unlimited. If this changes in the future, agent-reach will adapt in an update.

**Q: What is mcporter?**
A: A command-line bridge tool for the MCP protocol, used to call MCP servers. Agent Reach uses it to connect to Exa and XiaoHongShu.
