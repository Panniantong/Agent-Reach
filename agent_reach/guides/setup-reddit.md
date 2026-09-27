# Reddit Configuration Guide

## Function description

Reddit blocks almost all direct non-browser access (including datacenter and ISP proxy IPs) and the JSON API returns 403.

Agent Reach implements Reddit's search and reading functions through **rdt-cli**:
- **Search**: `rdt search "keywords"`
- **Read full post + comments**: `rdt read POST_ID`

Free, no proxy required, no API key required. Login authentication is required (`rdt login`, cookies are automatically extracted from the browser).

## Steps that Agent can automatically complete

1. Check whether rdt-cli is available:
```bash
which rdt && echo "installed" || echo "not installed"
```

2. If it is not installed, install it automatically (the PyPI version is temporarily behind, install the latest version from GitHub):
```bash
pipx install 'git+https://github.com/public-clis/rdt-cli.git'
```

Or install with one click:
```bash
agent-reach install --env=auto --system --channels=reddit
```

## Usage example

Search Reddit content:
```bash
rdt search "python best practices" -n 5
```

Read the full post and comments:
```bash
rdt read POST_ID
```

## Steps that need to be done manually by the user

none. After the user explicitly authorizes, rdt-cli passes
`agent-reach install --env=auto --system --channels=reddit` installation.

## Fallback: Exa Search

If you have Exa configured (via mcporter), you can also search Reddit content via Exa:

```bash
mcporter call exa.web_search_exa query="site:reddit.com python best practices" numResults=5
```

rdt-cli is the currently recommended solution and can be used without additional configuration.
