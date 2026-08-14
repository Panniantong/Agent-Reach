# Agent Reach productization workspace

This directory is the execution package for turning Agent Reach from a working personal installer into a production-grade **local-first** product. It is not the runtime. Runtime stays in `agent_reach/`.

**Current phase: 1 (contract truth + pins + doctor prose).** Phase 1 is executed on `phase-1-contract-hygiene` (uncommitted). Do not start Phase 2 from memory.

Canvas: [Agent Reach product plan](/Users/pepe/.cursor/projects/Users-pepe-Development-Agent-Reach/canvases/agent-reach-product-plan.canvas.tsx)

Security audit (do not re-litigate): [Agent Reach security audit](/Users/pepe/.cursor/projects/Users-pepe-Development-Agent-Reach/canvases/agent-reach-security-audit.canvas.tsx)

## Product in one sentence

Local-first installer + doctor + skill that makes AI agents able to read/search a curated set of internet backends safely. After install, agents call upstream tools directly. Agent Reach is glue + diagnostics + secret hygiene + policy enforcement, not a wrapper API.

## How to use this directory

1. Read this file, then `SCOPE.md` and `DECISIONS.md`. Those freeze the product.
2. Execute `ROADMAP.md` in order. Shippable units are `FEATURES.md` + `features/F01`–`F12`. Tick `CHECKLIST.md`.
3. Map security work through `SECURITY.md` (audit finding → phase). Do not invent new findings; implement the remediations.
4. Touch production code only as `ENGINEERING.md` describes. Public API, auth, deps, or broad refactors still need a yes, except the Phase 1 encodings in ADR-017.
5. Do not commit from this workspace unless Pepe asks.

## Documents

| File | What it answers |
|------|-----------------|
| `PRD.md` | Who, what, not-what, success metrics |
| `ARCHITECTURE.md` | What stays glue, what becomes product-grade |
| `SECURITY.md` | Audit remediations: severity, owner, phase |
| `ROADMAP.md` | Phases 0–5 with acceptance criteria |
| `FEATURES.md` | Master inventory of F1–F12 and every F*.* |
| `features/` | Full spec per parent feature (files, tests, AC, approval) |
| `CHECKLIST.md` | Tickable execution list by phase |
| `NEW-CHAT-PROMPT.md` | Paste into a new Cursor chat to start Phase 1 |
| `DIRECTORY.md` | Current repo vs target product layout |
| `SCOPE.md` | In / out: cookies, hosted SaaS, gh writes, MCP |
| `DECISIONS.md` | ADRs. Frozen unless Pepe reopens them |
| `CHANNELS.md` | Per-channel: commercial / extended / power-user |
| `ENGINEERING.md` | Convert without breaking existing CLI users |

## Frozen verdicts (from the audit)

- Leverage / fork the MIT installer + doctor + skill. Do not rewrite from zero.
- Do not productize as a hosted cookie proxy. Cookie platforms stay power-user optional / burner-only.
- Commercial core: GitHub + Exa + YouTube + RSS/Jina (official APIs / public CLIs). Cookie/OpenCLI is not the product.
- Phase 0 = plan + directory + canvas + feature inventory only. No channel rewrites, no CLI public API changes, no auth changes, no new runtime deps, no secret migration in this pass.

## Evidence baseline (v1.5.0, inspected 2026-08-13)

| Claim in marketing / CLAUDE.md | Reality in code |
|--------------------------------|-----------------|
| 13 platforms | 15 registered in `agent_reach/channels/__init__.py:26-42` |
| Channel contract is `can_handle` + `read` + `search` + `check` | `base.py:41-70` requires `can_handle` + `check` only |
| `core.py` is "read/search routing" | `AgentReach` exposes `doctor()` / `doctor_report()` only (`core.py:23-42`) |
| "entire internet" (`pyproject.toml:4`, `__init__.py:1`) | Curated 15-backend catalog |
| Version in three places including `tests/test_cli.py` | `pyproject.toml:3` and `__init__.py:4` are `1.5.0`. `tests/test_cli.py` uses `1.5.0` as fixture data for update comparison, never asserts `__version__` |
| Default install is safe | True: `cli.py:261` `safe_mode = not --system` |
| Secrets live in `~/.agent-reach/config.yaml` at 0600 | True: `config.py:46-103`. Not a secret manager |

## What this pass did not change

No edits to `agent_reach/` Python, CLI, tests, `pyproject.toml`, or skill runtime. Root `README.md` was not edited (it is a marketing homepage, not a docs index). Pointer from README to `product/` is a Phase 1 item.

## Next execution entry

Paste `NEW-CHAT-PROMPT.md` into a new chat. Phase 1 encodings (ADR-017): README pointer YES; drop skill check-update nudge YES; pyproject description text YES (no version bump, no release); `doctor --json` `confidence` field NO (prose-only doctor honesty).
