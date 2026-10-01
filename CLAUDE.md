# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project
Agent Reach is a Python CLI and library that gives AI agents read/search access to 16 internet platforms.
It installs, diagnoses and configures upstream tools. It is NOT a wrapper: after install, agents call the upstream tools directly (twitter-cli, yt-dlp, gh, mcporter, opencli, boss-agent-cli, …).
Repo: github.com/Panniantong/Agent-Reach | License: MIT | Version: 1.5.0

## Commands
- `pip install -c constraints.txt -e ".[dev]"`: dev install (the same command CI uses)
- `pytest -q`: all tests (CI runs this on Python 3.10–3.13 plus Windows)
- `pytest tests/test_boss_channel.py -v`: one file
- `pytest tests/test_cli.py -k is_newer_version -v`: a single test or a subset
- `ruff check agent_reach tests`: lint (rules E, F, I; line length 100, E501 ignored)
- `mypy agent_reach`: type check (tests are excluded)
- `bash test.sh`: full integration test (creates a venv, installs, runs doctor and the channel tests)
- `python -m agent_reach.cli doctor [--json]`: diagnostics
- `python -m agent_reach.cli install --env=auto`: auto-configure

CI (`.github/workflows/pytest.yml`) also has a **wheel-gate** job. It builds the real wheel, checks that `skill/SKILL.md`, `guides/`, `scripts/` and `skill/references/` ship inside it, and smoke-installs the wheel into a clean venv. If you add non-Python data files, make sure they end up in the wheel.

## Architecture
- **Channels** (`agent_reach/channels/`): one file per platform, each a subclass of `Channel` (`base.py`). The real contract is:
  - `can_handle(url)`
  - `check(config) -> (status, message)`, where status is `ok`/`warn`/`off`/`error`
  - class attributes `name`, `description`, `backends`, `tier` (0 = zero-config, 1 = needs a free key, 2 = needs setup)

  Channels do **not** implement `read`/`search`. Agents do the reading by calling upstream tools, guided by the skill files.
- **Backends**: `backends` is an ordered list of candidates. `check()` must set `self.active_backend` to the backend that actually works right now, or `None`. A user can force a backend with the config key `<channel>_backend` or the env var `<CHANNEL>_BACKEND`; `ordered_backends()` applies that override.
- **Probing** (`probe.py`): `shutil.which()` is not proof that a tool works, because stale venv shims pass `which()` and then fail to run. Use `probe_command()` inside `check()` so it tells apart missing, broken, timeout and error. Health checks must be read-only with no side effects. For example, `backends/opencli.py` avoids `opencli doctor` because that command auto-starts the daemon.
- **OpenCLI sites** (`channels/_opencli_site.py`): `OpenCLISiteChannel` is a thin base for platforms served only through OpenCLI (real Chrome plus a browser extension). It only needs `site`/`domains`/`usage`/`login_hint`.
- **Registry and doctor**: `channels/__init__.py::ALL_CHANNELS` is the only registry. `doctor.check_all()` loops over it. Each channel's exceptions are caught and reported as `error`, and every message is passed through `scrub_url_credentials` before output. `core.py` is just a thin `AgentReach` facade over doctor.
- **CLI** (`cli.py`, argparse, the bulk of the code): `setup`, `install`, `configure`, `doctor`, `uninstall`, `skill`, `format`, `transcribe`, `check-update`, `watch`, `version`.
- **Config** (`config.py`): YAML in the user's home, with env-var fallback. Writes are atomic and refuse symlinks (`ConfigSecurityError`). Tests in `test_private_file_writes.py`, `test_cookie_security.py` and others enforce file-permission and credential-hygiene rules.
- **Skill files** (`agent_reach/skill/`): `SKILL.md` and `SKILL_en.md` are the agent-facing routing table, with per-category detail in `references/*.md` (search, social, career, dev, web, video, finance). This is where usage commands for each platform live. `agent-reach skill` installs them into agent environments.
- Other pieces: `integrations/mcp_server.py` (MCP server), `cookie_extract.py` (browser cookie import), `transcribe.py` (Whisper via Groq/OpenAI), `utils/` (paths, subprocess env, URL host matching, text scrubbing), `config/mcporter.json`.

## Adding a channel
1. Add `channels/<platform>.py` and register an instance in `ALL_CHANNELS`. (CONTRIBUTING.md says to edit `doctor.py`, but that is outdated.)
2. Add `tests/test_<platform>_channel.py`. `test_channel_contracts.py` covers every registered channel automatically.
3. Update the platform count and routing in `skill/SKILL.md`, `skill/SKILL_en.md`, the right `skill/references/*.md`, README and CHANGELOG.

## Testing notes
- `tests/conftest.py` has autouse fixtures that point `HOME`/`XDG_CONFIG_HOME` at a temp dir and isolate cookie jars, so tests never touch the real user config. Keep new tests inside that isolation.
- Mock subprocess and `shutil.which` instead of calling real upstream tools (see `test_channel_contracts.py`).

## Conventions
- Python 3.10+ with type hints. Use `loguru` for logging and `rich` for CLI output. User-facing strings are mostly Chinese.
- Commit format: `type(scope): message`, one commit per change.
- All upstream tool calls go through a public API or CLI; never hack internals.

## Rules
- NEVER modify the source code of upstream open-source projects.
- Agent Reach is a "glue layer": it only routes and calls, it does not reimplement.
- The version must match in THREE places: `pyproject.toml`, `agent_reach/__init__.py`, `tests/test_cli.py`.
- Always work on a new branch and open a PR to main; never push to main directly.
- Run `pytest -q` before committing; all tests must pass.
- Cookie-based auth (Twitter, XHS): use only the Cookie-Editor export method, no QR scan. XHS QR login hangs.
