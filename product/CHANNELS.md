# Channels

Registry: `agent_reach/channels/__init__.py:26-42`. Count: **15**. Not 13 (`CLAUDE.md`). Not "10+" (`pyproject.toml:4`).

Contract in code (`base.py`): `can_handle` + `check`. Ordered `backends`. `check()` sets `active_backend` (None if unused/unverified).

Doctor "Never ok" is intentional: those checks refuse cookie-refresh, gh device-id writes, or live MCP. Phase 1 makes that readable without returning fake `ok`.

## Classification

| # | Channel | Product class | Auth today | Upstream | AR fetches? | Doctor can `ok`? | Disposition |
|---|---------|---------------|------------|----------|-------------|------------------|-------------|
| 1 | `github` | **Commercial** | gh login / `GH_TOKEN` / `github_token` | gh CLI | No | Never (warn) | Keep. Official CLI. Phase 4 read-only wrap. Phase 1 doctor honesty. |
| 2 | `exa_search` | **Commercial** | Exa MCP via mcporter (no key in current path) | mcporter | No | Never (warn if configured) | Keep. Official MCP. Doctor must say configured vs missing. |
| 3 | `youtube` | **Commercial** | none / optional cookies | yt-dlp | Transcribe CLI only | Yes | Keep. Public CLI. DNS-pin transcribe URLs in Phase 2. |
| 4 | `web` | **Commercial** | none | Jina Reader | Yes (`web.py:48-67`) | Always ok | Keep Jina. Pin or stop Python fetch; skill already uses `curl https://r.jina.ai/URL`. |
| 5 | `rss` | **Commercial** | none | feedparser (skill) | No (doctor import only) | Yes | Keep. Skill parses. Tighten `can_handle` (substring today, `rss.py:13-14`). |
| 6 | `v2ex` | Extended | none | V2EX public API | Yes | Yes | Keep as extended. Phase 2 pin or move to skill curl. |
| 7 | `bilibili` | Extended | none for search | bili-cli / OpenCLI / API | Doctor probe only | Can be ok | Keep as extended public search. OpenCLI subtitle path is power-user. |
| 8 | `xiaoyuzhou` | Extended | Groq/OpenAI key | ffmpeg + Whisper | Transcribe | Can be ok | Keep as extended. Official Whisper APIs. Keys go to keychain in Phase 3. |
| 9 | `linkedin` | Split | MCP browser login; Jina public pages | mcp-server-linkedin / Jina | No (Jina via web) | Never | Jina public pages = commercial-adjacent (use web). MCP login = **power-user**. |
| 10 | `twitter` | **Power-user** | Cookie-Editor | twitter-cli / OpenCLI / bird | No | Never | Gate. Burner only. Phase 3 inject-or-don't-store. No QR. No `--from-browser`. |
| 11 | `xiaohongshu` | **Power-user** | Cookie-Editor or existing Chrome session | OpenCLI / xhs-mcp / xhs-cli | Format only | Never | Gate. Cookie-Editor for MCP/legacy. OpenCLI does not get cookies injected (`SKILL.md:86-88`). Fix header-string flags Phase 2. |
| 12 | `reddit` | **Power-user** | browser session / rdt cookie | OpenCLI / rdt-cli | No | Never | Gate. No zero-config path (channel docstring). |
| 13 | `facebook` | **Power-user** | Chrome session | OpenCLI | No | Never | Gate. |
| 14 | `instagram` | **Power-user** | Chrome session | OpenCLI | No | Never | Gate. |
| 15 | `xueqiu` | **Power-user** | `xq_a_token` optional | Xueqiu HTTP APIs | Yes (cookie jar) | Can be ok | Gate. Owned fetch + process-global jar. Pin or stop fetch. `--from-browser` stays power-user. |

## Commercial core (the product)

Must work after a check-only install of tools the user already has, plus explicit `--system` for gh/mcporter/skill:

1. **GitHub** — `gh search`, `gh repo view`, issue/PR **read**. Auth is official. Writes out of default.
2. **Exa** — `mcporter call exa.web_search_exa ...` (`SKILL.md:60-61`).
3. **YouTube** — `yt-dlp` captions (`SKILL.md:69-70`). Not for Bilibili (skill already says so).
4. **Web** — Jina. Prefer skill curl. Python `read()` is extra surface.
5. **RSS** — feedparser in agent process.

These five names are the supported set. YouTube is a public CLI, not Google's official API; that is accepted (ADR-007).

## Power-user cookie / OpenCLI (not the product)

Twitter, XHS, Reddit, Facebook, Instagram, Xueqiu, LinkedIn MCP.

Rules:

- Opt-in via `--channels=` after `--system`.
- Burner accounts. README already warns; keep the warning, stop leading with these platforms.
- Cookie-Editor + stdin/getpass. Never paste into chat.
- Doctor does not refresh cookies. Phase 1 still reports configured vs missing.
- Do not reimplement scrapers. Do not modify upstream.

## What "keep / official-API / deprecate / power-user" means here

- **Keep** = stays in the registry.
- **Official-API / public CLI** = commercial or extended.
- **Power-user** = stays, gated.
- **Deprecate** = not used as a deletion plan for 1.5→product cut. Bird CLI is already labeled legacy in `twitter.py:37`. xhs-cli is a fallback in the XHS backend list. We do not delete them in Phases 1–4; we stop marketing them.

No channel is deleted in this conversion unless Pepe later asks. Gating is skill + install + docs.

## Per-channel engineering notes

### github (`channels/github.py`)

- Probes `gh --version` with telemetry env disabled (`_GH_READ_ONLY_ENV`).
- Reads `hosts.yml` without following symlinks; will not run `gh auth status` (writes device-id).
- Returns warn even when configured. Phase 1: prose in `format_report` + skill (F3.1). `confidence=configured` is F3.2, blocked until Pepe approves a JSON field.
- Skill `references/dev.md` is the write leak. Phase 4.

### exa_search (`channels/exa_search.py`)

- Needs `mcporter` on PATH and an `exa` server name in mcporter config.
- Will not start the remote MCP to verify. Correct. Report configured.

### youtube (`channels/youtube.py`)

- Can return ok. Transcribe is separate CLI surface (`cli.py` `transcribe`, `transcribe.py`).

### web (`channels/web.py`)

- `can_handle` is always True (fallback). `check` always ok, no network.
- `read()` hits Jina via urllib after `normalize_public_http_url` (no DNS pin).
- Skill uses curl. Product path can ignore `read()` if we delete it in Phase 2.

### rss (`channels/rss.py`)

- Doctor: import feedparser. Skill: `python3 -c "import feedparser..."`.
- `can_handle` substring: `/feed`, `/rss`, `.xml`, `atom`. Unused by core.

### v2ex (`channels/v2ex.py`)

- Owned public API client. Hardcoded HTTPS. User-Agent `agent-reach/1.0` in skill curl example (`SKILL.md:73`).
- Phase 2: pin or skill-only curl.

### twitter (`channels/twitter.py`)

- Ordered backends: twitter-cli, OpenCLI, bird.
- `twitter_cli_child_env` unused for spawn. Phase 3 ADR-004.
- `--from-browser` rejected in CLI.

### xiaohongshu (`channels/xiaohongshu.py`)

- OpenCLI preferred on desktop; MCP/legacy need Cookie-Editor.
- Header-string cookie flags insecure (`cli.py:1668-1690`). Phase 2.
- `format` CLI is xhs-only (`cli.py:152`).

### Others

Facebook/Instagram share `_opencli_site.py` (tier 1, never live-ok). Reddit has no zero-config path. Xueqiu holds a process-global CookieJar. LinkedIn inspects mcporter, never starts uvx for doctor.

## Install channel flags (`cli.py:265-277`)

`CHANNEL_INSTALLERS`: twitter, xiaoyuzhou, xiaohongshu, reddit, facebook, instagram, bilibili, opencli. `xueqiu` and `linkedin` are cookie/manual (no installer). GitHub/YouTube/Web/RSS/Exa are "core" relative to `--channels=` optional list.

Phase 4 should make the default `--system` path install commercial core only; cookie platforms require explicit names, and `--channels=all` should print the burner warning.
