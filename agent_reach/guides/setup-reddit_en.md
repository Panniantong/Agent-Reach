# Reddit Setup Guide

## Overview
Reddit blocks almost all non-browser access (datacenter and ISP proxy IPs return 403).

Agent Reach uses **rdt-cli** for Reddit search and reading:
- **Search**: `rdt search "query"`
- **Read full posts + comments**: `rdt read POST_ID`

Free, no proxy, no API key needed.

## Agent Can Auto-Configure

1. Check if rdt-cli is available:
   ```bash
   which rdt
   ```

2. If not installed, auto-install:
   ```bash
   pipx install rdt-cli
   ```
   Or one-liner:
   ```bash
   pipx install 'rdt-cli>=0.4.2'
   ```

## Usage Examples

```bash
# Search Reddit
rdt search "rust programming" --limit 10

# Read full post
rdt read abc123
```

## User Action Required

None. rdt-cli is auto-installed by `agent-reach install --env=auto`.

## Fallback: Exa Search

If Exa is configured (via mcporter), search Reddit through Exa:
```bash
mcporter call 'exa.web_search_exa(query: "site:reddit.com query", numResults: 5)'
```
