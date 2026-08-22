# Dependency Locking Guide

Agent Reach uses `constraints.txt` as a reproducible dependency baseline.

This is the **default user install/upgrade path**, not only a dev/CI trick. CI already installs with `-c constraints.txt`. Documented `pip install` recipes in `docs/install.md` and `docs/update.md` must do the same.

`pyproject.toml` keeps version ranges for flexibility. Pins live in `constraints.txt`. Do not freeze the ranges in `pyproject.toml` without a dedicated PR.

## Why

- Keep local/CI/user dependency graph stable
- yt-dlp talks to the internet; zip-from-main without pins drifts from CI
- Make regression results easier to compare

## Default user path

Fetch `constraints.txt` from the **same git ref** as the package (the file is also inside the GitHub zip):

```bash
curl -fsSL -o /tmp/agent-reach-constraints.txt \
  https://raw.githubusercontent.com/Panniantong/agent-reach/main/constraints.txt
python3 -m venv ~/.agent-reach-venv
source ~/.agent-reach-venv/bin/activate
pip install -c /tmp/agent-reach-constraints.txt \
  https://github.com/Panniantong/agent-reach/archive/main.zip
```

**pipx cannot take `-c`.** Prefer the venv recipe. From a git checkout you can `pip install -c constraints.txt .` or `pipx install -e .` for development only (that still does not apply the constraint file to pipx's resolver).

## Dev install with constraints

```bash
pip install -c constraints.txt -e '.[dev]'
```

## Update workflow

1. Update `pyproject.toml` dependency ranges as needed.
2. Validate against latest compatible versions locally.
3. Update pinned versions in `constraints.txt`.
4. Run validation:

```bash
pytest -q
ruff check agent_reach tests
mypy agent_reach
```

5. Open PR with dependency and validation notes.
