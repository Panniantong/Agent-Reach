# Browser Cookie Import

This fork only supports browser cookie import for Twitter/X.

```powershell
agent-reach configure --from-browser chrome
```

Requirements:

- `browser-cookie3` installed with the package
- the selected browser is closed
- you are already logged into `x.com`

Manual input is still supported:

```powershell
agent-reach configure twitter-cookies "auth_token=...; ct0=..."
```
