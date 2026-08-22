# Scope

If it is not in this file, it is not the product. Frozen unless Pepe reopens a decision in `DECISIONS.md`.

## In scope (the product)

- Local-first installer (`agent-reach install --env=auto` check-only default).
- Doctor (`agent-reach doctor` / `--json`) as the health signal.
- Skill pack (`agent_reach/skill/SKILL.md` + `references/`) that routes agents to upstream binaries.
- Config + secret hygiene (`~/.agent-reach/`, later OS keychain).
- Commercial channels: GitHub (`gh`), Exa (`mcporter` + Exa MCP), YouTube (`yt-dlp`), Web (Jina), RSS (`feedparser`).
- Policy: read-only GitHub in the default skill; cookie platforms gated.
- SSRF hardening for any remaining in-process fetch, or moving fetch 100% upstream.
- Dependency pinning on the default install path.
- Docs/contract truth (15 channels, `can_handle` + `check`, no "entire internet"). Execution breakdown: `FEATURES.md`.
- MCP `get_status` as a read-only status surface (`integrations/mcp_server.py`).
- Uninstall, dry-run, `--safe` compatibility flag.
- Tests for security-relevant paths.
- Packaging / CI / versioning as a real product (Phase 5).

## In scope as power-user optional (not marketed as the product)

These stay in the repo. They are not the commercial core. They require an explicit `--channels=` opt-in, burner-account warning, and Cookie-Editor / existing Chrome session. No QR. No hosted cookies.

- Twitter / X (`twitter-cli`, OpenCLI, bird legacy)
- XiaoHongShu (OpenCLI / xiaohongshu-mcp / xhs-cli)
- Reddit (OpenCLI / rdt-cli)
- Facebook (OpenCLI)
- Instagram (OpenCLI)
- Xueqiu (owned HTTP + optional `xq_a_token`)
- LinkedIn MCP (`mcp-server-linkedin` browser login). LinkedIn-via-Jina is the commercial-adjacent fallback and lives under Web.

## Extended (keep, not commercial headline)

Public or official, not cookie session theft, not in the four-name commercial headline:

- V2EX public JSON API (owned fetch today; Phase 2 must DNS-pin or push to skill `curl`)
- Bilibili search via `bili-cli` (no login for search)
- Xiaoyuzhou transcription via Groq/OpenAI Whisper keys + ffmpeg (`transcribe` CLI)

## Out of scope (do not build)

| Item | Why |
|------|-----|
| Hosting other people's cookies | Audit verdict. Account takeover + ToS + no tenancy. |
| Multi-tenant SaaS proxy | Same. Local-first is the trust model. |
| QR login | Hangs / violates Cookie-Editor-only policy (`CLAUDE.md`). |
| Reimplementing Twitter / XHS / Reddit scrapers | Glue, not a scraping engine. Never modify upstream OSS. |
| Mutating upstream tool internals | `CLAUDE.md`: public API/CLI only. |
| Making `--system` the documented one-liner | Writes `~/.claude/skills`, `~/.openclaw/skills`, `~/.config/opencode/skills`, `~/.agents/skills` plus apt/brew/npm (`cli.py:541-547`, `cli.py:697-752`). |
| MCP tools that hold cookies in-process | MCP stays status/doctor. |
| GitHub writes as default skill behavior | Marketing is read/search. `skill/references/dev.md` currently unlocks `gh issue create`, `gh pr create`, `gh repo fork`. |
| browser-cookie3 for Twitter/XHS | Already blocked (`cli.py:190-194`). Do not reopen. `--from-browser` remains for xueqiu/bilibili until Phase 4 gates it. |
| "Entire internet" positioning | 15 curated backends. |
| Public HTTP wrapper API in front of channels | Contradicts "not a wrapper". `AgentReach` stays doctor-only. |
| Changing CLI public API in Phase 0 | This pass is plan + scaffolding only. |

## GitHub writes

- **In:** `gh` as the official GitHub client for **read/search**: `gh search`, `gh repo view`, `gh issue list`, `gh pr view`, `gh api` GET-equivalent.
- **Out of default:** `gh issue create`, `gh pr create`, `gh repo create`, `gh repo fork`, `gh release create`, anything that mutates.
- **Enforcement (Phase 4):** skill text is not enough. Wrap or constrain `gh` (wrapper script, `GH_PROMPT_DISABLED` + allowlist, or a tiny `agent-reach gh` proxy). Pepe must approve the mechanism. Do not ship a wrapper that changes the `gh` binary on PATH without an explicit flag.

## MCP

- **In:** `get_status` over stdio, config opened `read_only=True` (`mcp_server.py:40-55`).
- **Out:** wrapping twitter/xhs/reddit as MCP tools that hold sessions. Do not grow the MCP surface unless Pepe names a product reason.

## Cookies

- **In as power-user:** Cookie-Editor export, `configure twitter-cookies` / `xhs-cookies` via **stdin or getpass**, never argv, never agent-chat paste as docs.
- **Out:** QR, Chrome auto-extract for Twitter/XHS, cookie-in-chat happy path (`docs/cookie-export.md:17-27`, `SKILL.md:142`), syncing cookies to a server Agent Reach operates.

## What we will not rewrite

`agent_reach/cli.py`, `doctor.py`, `config.py`, channel files, `probe.py`, `utils/paths.py`, `utils/url.py` host matching, cookie-refresh refusal tests. We **harden and tell the truth**. We do not replace the installer with a new framework.
