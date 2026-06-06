# Exa Search Setup Guide

## Overview
Exa is an AI semantic search engine accessed via MCP. **Free, no API key needed**.

## Agent Can Auto-Configure

`agent-reach install --env=auto` handles this automatically.

### 1. Install mcporter
```bash
npm install -g mcporter
```

### 2. Register Exa MCP
```bash
mcporter config add exa https://mcp.exa.ai/mcp
```

### 3. Verify
```bash
mcporter call 'exa.web_search_exa(query: "test", numResults: 1)'
```

## User Action Required

**None.** Exa is free via MCP — no signup, no API key needed.

If `agent-reach install` failed to configure it due to network issues, run the two commands above manually.