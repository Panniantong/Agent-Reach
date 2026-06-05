# Reddit Setup Guide

## Overview

Reddit blocks almost all non-browser direct access (including data center and ISP proxy IPs), and the JSON API returns 403.

Agent Reach implements Reddit search and reading via **rdt-cli**:
- **Search**: `rdt search "keyword"`
- **Read full post + comments**: `rdt read POST_ID`

Free, with no proxy, no API key, and no login required.

## Steps the Agent Can Complete Automatically

1. Check whether rdt-cli is available:
```bash
which rdt && echo "installed" || echo "not installed"
```

2. If not installed, install it automatically:
```bash
pipx install rdt-cli
```

Or install in one step:
```bash
agent-reach install --env=auto --channels=reddit
```

## Usage Examples

Search Reddit content:
```bash
rdt search "python best practices" -n 5
```

Read a full post and its comments:
```bash
rdt read POST_ID
```

## Steps the User Must Do Manually

None. rdt-cli is installed automatically via `agent-reach install --env=auto`.

## Fallback: Exa Search

If you have already configured Exa (via mcporter), you can also search Reddit content through Exa:

```bash
mcporter call 'exa.web_search_exa(query: "python best practices", numResults: 5, includeDomains: ["reddit.com"])'
```

rdt-cli is the currently recommended solution and works without any additional configuration.
