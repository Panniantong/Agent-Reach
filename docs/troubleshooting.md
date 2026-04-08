# Troubleshooting

## `doctor` says GitHub is not authenticated

Run:

```powershell
gh auth login
```

Or store a token explicitly:

```powershell
agent-reach configure github-token YOUR_TOKEN
```

## `doctor` says Twitter/X is not authenticated

Run one of:

```powershell
agent-reach configure twitter-cookies "auth_token=...; ct0=..."
agent-reach configure --from-browser chrome
```

## `doctor` says Exa is not configured

Run:

```powershell
mcporter --config "$HOME\.mcporter\mcporter.json" config add exa https://mcp.exa.ai/mcp
```

## `doctor` says YouTube needs a JS runtime

Install Node.js LTS with `winget`, then run the fix command printed by `doctor`.
