# Dependency Notes

The Windows/Codex fork keeps runtime dependencies intentionally small:

- Python packages for CLI behavior, RSS parsing, YAML config, and browser cookie import
- Windows-installed CLIs for `gh`, `yt-dlp`, `mcporter`, and optional `twitter-cli`

When `pyproject.toml` changes, refresh the lock file locally:

```powershell
uv lock
```

Then validate the repo:

```powershell
python -m pytest
uvx ruff check .
uvx mypy agent_reach
uvx --from build pyproject-build --wheel --sdist
```
