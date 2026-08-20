# Holistic Review Agent Prompt

Borrowed from claude-review-loop `stop-hook.sh` Agent 2.

## Scope

Whole-project structure — not line-by-line diff only.

Read: top-level dirs, `README*`, `AGENTS.md`, `CLAUDE.md`, `pyproject.toml`, CI configs.

## Criteria

### Organization
- Logical layout; new files in sensible places
- Separation of concerns (config / business / CLI / tests)
- No god modules; shared code extracted

### Agent harness
- `AGENTS.md` documents conventions, commands, non-obvious env
- Evolved config not duplicated in static JSON when harness mode is on
- Clear test entrypoints (`python3 -m pytest -q`, not bare `pytest`)

### Architecture
- No circular imports
- External integrations behind adapters (Agent Reach: upstream tools not patched)
- Centralized config via `effective_settings()` / loaders

## Output format

```
severity: critical|high|medium|low
category: Holistic
location: path/ or directory
description: ...
suggested_fix: ...
```
