# Next chat prompt

Phase 0 docs are done. Copy the block below into a **new** Cursor agent chat with this repo open. Do not start Phase 2–5 in that chat.

---

## Copy from here

```
You are founder-side engineering for Pepe on Agent Reach at /Users/pepe/Development/Agent-Reach.

Tone: direct, casual, no fluff, no em dashes. Call him Pepe when natural. Smallest viable change. Match existing patterns. Do not add runtime deps. Do not change auth or secret storage. Do not implement Phase 2-5.

You have NO memory of prior chats. Product source of truth is product/ in this repo. Read before editing, in this order:
- CLAUDE.md
- product/README.md
- product/ROADMAP.md
- product/FEATURES.md
- product/features/F01-contract-truth.md
- product/features/F02-install-hygiene.md
- product/features/F03-doctor-honesty.md
- product/features/F08-channel-productization.md (F8.1 docs slice only)
- product/features/F09-mcp.md (F9.2 docs only)
- product/features/F11-tests-ci.md (F11.1-F11.3)
- product/features/F12-telemetry-update.md
- product/CHECKLIST.md (Phase 1 section)
- product/SCOPE.md
- product/DECISIONS.md (especially ADR-017)
- product/ENGINEERING.md

Also open if needed: product/CHANNELS.md, product/SECURITY.md, product/ARCHITECTURE.md, product/DIRECTORY.md, product/PRD.md.

Canvases (do not delete; do not re-litigate the audit):
- /Users/pepe/.cursor/projects/Users-pepe-Development-Agent-Reach/canvases/agent-reach-product-plan.canvas.tsx
- /Users/pepe/.cursor/projects/Users-pepe-Development-Agent-Reach/canvases/agent-reach-security-audit.canvas.tsx

## Frozen product
Local-first installer + doctor + skill. After install, agents call upstream tools directly. NOT a wrapper API. NOT a hosted cookie proxy. Commercial core: GitHub, Exa, YouTube, RSS/Jina. Cookie/OpenCLI is power-user / burner only. 15 channels in agent_reach/channels/__init__.py. Contract is can_handle + check (base.py). AgentReach is doctor-only (core.py). Check-only install is the default (cli.py safe_mode). Never weaken tests/test_doctor_credential_boundaries.py. Never push to main. New branch, PR to main. Do not commit unless Pepe asks. Version is 1.5.0 and must NOT change in this chat. Version in three places if it ever changes: pyproject.toml, agent_reach/__init__.py, and the assert test (you will ADD the assert; you will NOT bump the number).

## This chat is Phase 1 only
Execute product/CHECKLIST.md Phase 1. Feature IDs: F1.1-F1.11, F2.1-F2.6, F2.8-F2.9, F3.1, F3.3-F3.4, F8.1 (docs only), F9.2 (docs only), F11.1-F11.3, F12.1-F12.3.

Do NOT do: F3.2, F3.5, F2.7, F4 (except the skill cookie line which is F1.3), F5, F6, F7, F8.2-F8.4, F9.1 changes, F10, F11.4-F11.6, F12.4.

## Phase 1 approval encodings (already decided)
1. README pointer to product/: YES. Add it. Docs, not API.
2. Drop skill check-update nudge: YES. Edit SKILL.md and SKILL_en.md standing rule. Keep the check-update CLI command. Skill copy, not runtime API.
3. pyproject description wording: YES if you only change the description string (and matching "entire internet" docstrings/help in __init__.py, core.py, cli.py argparse description). NO version bump. NO keywords/classifiers/deps/scripts. NO publish. That is not a release.
4. doctor --json confidence field: NO. Skip F3.2. Public API. Leave it blocked pending Pepe. Phase 1 doctor honesty is prose only: format_report legend + skill text. Do not add or remove JSON keys. status stays ok|warn|off|error. Do not remap warn to ok for github/twitter/xhs/reddit/exa/linkedin/opencli.

## What to change (inspect first, then smallest edit)
Contract truth: CLAUDE.md 15 channels and can_handle+check; core.py is not a router; CONTRIBUTING.md must not say update doctor.py to register a channel; docs/install.md config.yaml not config.json; README commercial story + GitHub row must not advertise Issue/PR/Fork as the unlock; translations docs/README_en.md (JA/KO if they repeat entire internet); skill dual-language kill "用户只需提供 cookies" / "The user only provides cookies"; skill drop post-task check-update; skill zero-config count honest or removed.

Install docs: constraints.txt on the default pip path; pipx cannot take -c so say so; copy-paste one-liner is check-only; --system blast radius lists ~/.claude/skills, ~/.openclaw/skills, ~/.config/opencode/skills, ~/.agents/skills plus apt/brew/npm plus mcporter; docs/update.md same constraints rule; docs/dependency-locking.md is the user path not just dev.

Doctor: format_report must not imply non-ok channels are broken; document which channels never return ok (see CHANNELS.md). JSON schema freeze.

MCP: mcp_server.py currently advertises extra [mcp] which does not exist in pyproject.toml. Fix the message to match extras that exist (all / mcp[cli] separately). Do not add an extra.

Tests: add version equality assert (read pyproject, compare to agent_reach.__version__, still 1.5.0). len(get_all_channels()) == 15. New tests/test_docs_contract.py (preferred) for the greps in F11.1 and F11.3. Update test_doctor.py legend expectations if you change format_report. Do not weaken existing security tests.

## Git / process
- New branch from main. Never push main.
- Do not commit unless Pepe asks. When he asks: pytest tests/ -v must be green first. Commit format type(scope): message.
- If you would touch public CLI flags, doctor JSON keys, auth, or add a dependency: stop and ask. Phase 1 should not need those.

## Final response format
Changed:
Tests:
Risks:
Next:

In Next, list remaining work from FEATURES.md / CHECKLIST.md after Phase 1 (Phase 2+). Do not start it. Stop when Phase 1 checklist is done or you are blocked on a real file conflict.
```

---

## After you paste

That chat implements Phase 1. This file is not the implementation. Do not commit Phase 0 docs until Pepe asks.
