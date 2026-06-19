# AGENTS.md

## Project
Agent Reach is a Python CLI + library that gives AI agents read/search access to internet platforms.
It is a capability layer and installer/doctor for upstream tools — not a wrapper around them.

## What to read first
- `README.md` for the public-facing overview and supported platforms
- `docs/install.md` and `docs/update.md` for install/update flow
- `docs/troubleshooting.md` for common failure modes
- `CLAUDE.md` for the repo's detailed agent notes and conventions

## Working rules
- Prefer the smallest safe change that solves the actual problem.
- Do not re-architect upstream tools or invent new scraping paths when an existing backend works.
- Keep changes aligned with the repo's "glue layer" design: route and call upstream tools directly.
- If behavior changes, update tests and docs together.
- Run the relevant tests before claiming success; for broad changes, use `pytest tests/ -v`.
- Keep version numbers in sync across `pyproject.toml`, `agent_reach/__init__.py`, and `tests/test_cli.py`.
- Use a feature branch; do not push directly to `main`.

## Platform/auth conventions
- Cookie-based auth for Twitter/XHS: use Cookie-Editor export, not QR scan.
- Treat local credentials as local-only; do not upload tokens/cookies into the repo.
- Follow the installer's safe mode when an environment is uncertain.

## Useful commands
- `python -m agent_reach.cli doctor`
- `python -m agent_reach.cli install --env=auto`
- `pytest tests/ -v`
- `bash test.sh`

## Notes for multi-agent setups
- Hermes, Codex, OpenCode, Claude Code, and similar agents should all follow this file.
- If a tool has its own project-memory file, this repo should still use the same shared conventions above.
