# CLAUDE.md

## Project
Agent Reach is a Windows-first Python CLI for Codex-style research workflows.
Supported channels: `web`, `exa_search`, `github`, `youtube`, `rss`, and optional `twitter`.

## Commands
- `python -m pytest`
- `uvx ruff check .`
- `uvx mypy agent_reach`
- `uvx --from build pyproject-build --wheel --sdist`
- `python -m agent_reach.cli doctor`
- `python -m agent_reach.cli install --env=auto`

## Structure
- `agent_reach/cli.py` - CLI entry point
- `agent_reach/core.py` - health-check wrapper
- `agent_reach/config.py` - YAML config handling
- `agent_reach/doctor.py` - doctor output
- `agent_reach/channels/` - supported channel checks
- `agent_reach/skill/` - bundled Codex skill
- `docs/` - Windows/Codex-facing docs
- `tests/` - pytest suite

## Rules
- Keep the public surface aligned with the supported channels only.
- Prefer Windows-native install paths and commands.
- Do not reintroduce hidden legacy channels through docs, tests, or CLI help.
- Keep `pyproject.toml`, `agent_reach/__init__.py`, and tests consistent when versioning changes.
