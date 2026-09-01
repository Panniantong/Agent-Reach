# PRD — Agent Reach as a product

Status: Phase 0 freeze. Version target: keep `1.5.0` until Phase 5 cuts a product release. License: MIT (`LICENSE`, copyright "Agent Eyes" 2025).

## Problem

AI agents can write code. They cannot reliably read the internet without each user reinventing tool selection, install, auth, and health checks. Agent Reach already solves selection + install + doctor for 15 backends. It is not yet a product: docs lie about the contract, secrets are pasted into agent chat, doctor under-reports working backends, GitHub writes are unlocked by the skill, and three channels fetch inside this repo.

## Who it is for

Primary: Pepe (and operators like him) running local or self-hosted coding agents (Claude Code, Cursor, OpenClaw, OpenCode, Windsurf) who want a **safe default** set of read/search backends.

Secondary: advanced users who opt into cookie/OpenCLI platforms with burner accounts. They are not the commercial story. They are a gated extra.

Not a customer: anyone who wants Agent Reach to hold their Twitter/XHS cookies on a server, or a multi-tenant "search API" that wraps those sessions.

## What it is

A local-first **capability layer**:

1. **Install** — check-only by default. `--system` is explicit, warned, and never the documented one-liner.
2. **Doctor** — honest signal of what is installed, configured, and (where safe) live. Login channels stay un-probed for cookie refresh; they still report a usable "ready vs missing" distinction.
3. **Skill** — routing table that tells the agent which upstream binary to run. After install, agents call `gh`, `yt-dlp`, `mcporter`, `curl https://r.jina.ai/...`, `feedparser` directly.
4. **Secret hygiene** — OS keychain (Phase 3). Cookie-Editor remains power-user. Stdin/getpass is the only cookie path. Never paste cookies into agent chat as the happy path.
5. **Policy enforcement** — read-only for GitHub in the default skill; commercial channels are official APIs / public CLIs only.

Positioning in `core.py:1-8` is the product: installer, doctor, config. Not a wrapper. Keep it.

## What it is not

- A hosted cookie proxy or multi-tenant SaaS.
- A scraping engine. Channel files are a catalog + probe adapters (`channels/__init__.py` docstring: "lists all supported platforms for doctor checks").
- A URL router. Nothing in production dispatches `can_handle` into `read()`. `WebChannel.read` exists (`web.py:48-67`) but `AgentReach` does not call it.
- QR login. Cookie-Editor export only for Twitter/XHS (`CLAUDE.md`, `cli.py:190-194` blocks `--from-browser` for those two).
- A rewrite of twitter-cli, OpenCLI, xhs-cli, rdt-cli, or gh internals.

Full out-of-scope list: `SCOPE.md`.

## Jobs to be done

| Job | Success looks like |
|-----|--------------------|
| New agent, official backends only | `install --env=auto` (check-only), then explicit `--system` after user consent. GitHub + Exa + YouTube + RSS/Jina work. Skill forbids writes. |
| Know what works | `doctor --json` is a signal the agent can trust. Login channels say "configured, unverified" not a false "off". |
| Put in a secret without leaking it to the cloud transcript | Stdin/getpass or keychain. Docs never say "paste cookies to your agent". |
| Power user wants Twitter on a burner | Gated path. Cookie-Editor → stdin. Burner-only warning. Not in the default commercial set. |
| Uninstall | `uninstall` removes `~/.agent-reach/`, skill copies, mcporter bits. Already exists (`cli.py:1826`). Keep it. |

## Commercial channel set (supported)

These are the product. Official APIs or public CLIs. No session cookies required.

| Channel | Upstream | Auth |
|---------|----------|------|
| GitHub | `gh` CLI | `gh auth login` / `GH_TOKEN` (read-only default) |
| Exa | Exa MCP via `mcporter` | Exa MCP (no key in current install path) |
| YouTube | `yt-dlp` | none for public captions |
| Web | Jina Reader (`https://r.jina.ai/...`) | none |
| RSS | `feedparser` in the agent process (skill), doctor checks import | none |

Everything else is extended or power-user. See `CHANNELS.md`. Cookie/OpenCLI is not sold, marketed, or default-installed as the product.

## Production-grade bar (must all be true to call it a product)

1. Secrets: OS keychain (or equivalent). Never YAML cookies as the product path. Never paste cookies into agent chat as the documented happy path.
2. Official APIs / public CLIs only for supported commercial channels.
3. Read-only enforced where possible (especially GitHub: wrap or constrain `gh`; skill must not unlock writes as the default).
4. SSRF: DNS-pin or stop in-process fetch (Web / V2EX / Xueqiu). No hostname-rebinding holes.
5. `install --system` is not the default documented path. Check-only default stays. Blast radius documented.
6. Pin dependencies (`constraints.txt` on the default install path). CI already uses it (`.github/workflows/pytest.yml:26`). Users do not.
7. Doctor is a real signal. Fix login-channel false-negatives without weakening the cookie-refresh refusal (`tests/test_doctor_credential_boundaries.py`).
8. Align `CLAUDE.md` / README with reality: 15 channels, `can_handle` + `check`, no "entire internet".
9. MCP stays status/doctor oriented unless a new product reason appears (`integrations/mcp_server.py` is `get_status` only, config `read_only=True`).
10. Tests for security-relevant paths. 33 test modules exist; gaps are DNS-pin, keychain, gh read-only wrapper, cookie-in-chat docs regression.
11. Twitter config lie fixed in Phase 3: inject env into the child, or stop storing unused tokens. Today `configure twitter-cookies` writes YAML (`cli.py` configure path); `twitter_cli_child_env` can inject (`twitter.py:12-31`) but nothing in the product spawn path uses it; `SKILL.md:81-84` still tells the agent to set process env.
12. Version still in three places, and the third place actually asserts: `pyproject.toml`, `__init__.py`, `tests/test_cli.py`.

## Success metrics

Ship metrics, not vanity:

| Metric | Now (v1.5.0) | Product bar |
|--------|--------------|-------------|
| Documented channel count | CLAUDE.md 13, README table 15, pyproject "10+" | 15 everywhere, classified |
| Doctor channels that can return `ok` | 7 of 15 | Commercial set can return `ok` or an explicit `ready` without live cookie probes |
| Cookie paste in happy-path docs | `docs/cookie-export.md:17-27`, `SKILL.md:142` | Zero. Stdin/getpass only |
| Default install mutates system | No (`cli.py:261`) | Still no. Docs match |
| `constraints.txt` on user install | CI only | Default git/zip/pipx path |
| Skill GitHub examples include writes | `skill/references/dev.md:21-45` (`gh issue create`, `gh pr create`, `gh repo fork`) | Read-only default; writes behind explicit opt-in |
| SSRF DNS pin | Literal IPs only (`utils/url.py:47-84`, `transcribe.py:214-247`) | Resolve + pin, or no in-process fetch |
| Secrets at rest | YAML 0600 | Keychain for product path |
| Version test | No `__version__` equality assert | Three-place assert |

## Non-goals this year

- Hosting other people's cookies.
- Reimplementing Twitter / XHS / Reddit scrapers.
- Mutating upstream tool internals.
- Turning MCP into a cookie-holding tool server.
- QR login.
- A public HTTP API in front of channels.

## Positioning vs the current README

Keep: installer + doctor + skill, multi-backend routing as a catalog, MIT, local secrets, check-only default.

Kill as product claims: "entire internet", "给你的 AI Agent 一键装上互联网能力" as if cookie platforms were the default, GitHub "提 Issue/PR、Fork" as a supported unlock, "用户只需提供 cookies" (`SKILL.md:142`).

Replace with: curated official-API backends by default; power-user cookie platforms behind a wall and a burner warning.
