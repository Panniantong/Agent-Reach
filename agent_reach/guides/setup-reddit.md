# Reddit Setup Guide

## Features

Reddit has blocked almost all direct non-browser access (including datacenter and ISP proxy IPs), JSON API returns 403.

Agent Reach implements Reddit search and reading functionality through **rdt-cli**:
- **Search**: `rdt search "keyword"`
- **Read full post + comments**: `rdt read POST_ID`

Free, no proxy needed, no API key required. Requires login authentication (`rdt login`, automatically extracts cookies from browser).

## Steps Agent Can Complete Automatically

1. Check if rdt-cli is available:
```bash
which rdt && echo "installed" || echo "not installed"
```

2. If not installed, automatically install (PyPI version lags, install latest from GitHub):
```bash
pipx install 'git+https://github.com/public-clis/rdt-cli.git'
```

Or one-click install:
```bash
agent-reach install --env=auto --channels=reddit
```

## Usage Examples

Search Reddit content:
```bash
rdt search "python best practices" -n 5
```

Read full post and comments:
```bash
rdt read POST_ID
```

## Manual User Steps

None. rdt-cli is automatically installed via `agent-reach install --env=auto`.

## Fallback: Exa Search

If you have configured Exa (via mcporter), you can also search Reddit content through Exa:

```bash
mcporter call 'exa.web_search_exa(query: "python best practices", numResults: 5, includeDomains: ["reddit.com"])'
```

rdt-cli is the currently recommended solution with no additional configuration needed.
