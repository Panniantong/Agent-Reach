# Updating Agent Reach

Update the local checkout, then reinstall the tool from source:

```powershell
git pull --ff-only
uv tool install . --reinstall
agent-reach doctor
```

If you changed dependencies or metadata, refresh the lock file too:

```powershell
uv lock
```
