# Architecture — target vs now

Agent Reach stays an installer + doctor + skill. Production-grade means policy and hygiene around that glue, not a new runtime.

## What the code actually is (v1.5.0)

```
Agent
  ├─ SKILL.md (copied into ~/.claude/skills, ~/.openclaw/skills, …)
  │     └─ tells agent to exec: gh, yt-dlp, mcporter, twitter, opencli, curl jina, feedparser
  ├─ agent-reach CLI (cli.py)
  │     ├─ install (check-only default; --system writes skills + OS packages)
  │     ├─ doctor  → doctor.py → channels/*.check()
  │     ├─ configure → config.yaml (0600) / cookie_extract.py
  │     ├─ transcribe → yt-dlp + Whisper APIs
  │     ├─ skill / uninstall / check-update / watch / format
  │     └─ MCP stdio: get_status only (integrations/mcp_server.py)
  └─ owned HTTP (exception): web.py, v2ex.py, xueqiu.py
```

Evidence:

- `core.py:1-8` and `AgentReach` (`core.py:23-42`): doctor only. No URL router.
- Channel contract in code: `can_handle` + `check` (`base.py:6-9`, `base.py:41-70`). `read`/`search` are not required. Only `WebChannel.read`, V2EX helpers, and Xueqiu helpers fetch.
- Registry: 15 channels (`channels/__init__.py:26-42`).
- After install, agents call upstream. True for Twitter, Reddit, Facebook, Instagram, XHS, LinkedIn MCP, GitHub, YouTube, Exa, Bilibili. False for Web (Jina via urllib), V2EX, Xueqiu. RSS doctor-checks `feedparser`; the skill imports it in the agent process (`skill/references/web.md:32-39`).

## What stays (do not rewrite)

| Piece | Why it is the product |
|-------|----------------------|
| `cli.py` install/doctor/configure/uninstall | UX. Default check-only is already correct (`cli.py:261`). |
| `doctor.py` + `channels/*.check()` | Catalog + health. |
| `config.py` atomic 0600 YAML, symlink refusal | Keep as fallback; keychain becomes the product path in Phase 3. |
| `probe.py` argv-list probes, no `shell=True` | Keep. |
| `utils/paths.py` private writes | Keep. |
| `utils/url.py` `host_matches` | Keep. DNS-pin is additive. |
| Cookie-Editor-only for Twitter/XHS | Keep. |
| Doctor cookie-refresh refusal | Keep (`tests/test_doctor_credential_boundaries.py`). |
| MCP `get_status` | Keep status-only. |
| Skill as markdown routing table | Keep. Edit policy text; do not turn it into a runtime. |

## What becomes product-grade (without becoming a wrapper API)

| Concern | Now | Target |
|---------|-----|--------|
| Commercial set | All 15 marketed equally; README unlocks GitHub writes | Default story is GitHub + Exa + YouTube + RSS/Jina. Others gated. |
| Secrets | YAML 0600; docs say paste cookies to the agent | Keychain for product secrets. Cookie path is stdin/getpass, power-user only. |
| GitHub policy | Skill includes create/fork (`skill/references/dev.md`) | Read-only default + enforcement wrapper (Phase 4). |
| SSRF | Literal IP denylist, skip DNS (`utils/url.py:47-84`) | DNS resolve + pin to global unicast, or delete in-process fetch. |
| Doctor signal | 8 channels never `ok` by design | Structured status: `ok` / `ready-unverified` / `missing`. Never run cookie-refreshing CLIs. |
| Install docs | README one-liner can still lead agents to `--system` | Check-only is the only copy-paste. `--system` has a blast-radius block. |
| Deps | Ranges in `pyproject.toml:30-37`; `constraints.txt` is CI-only | Default install uses `-c constraints.txt`. |
| Owned fetch | web / v2ex / xueqiu inside this repo | Prefer skill `curl` / upstream. If AR still fetches, it DNS-pins. |
| Twitter tokens | Written to YAML, unused by `twitter` spawn | Inject into child env **or** stop storing. |

## Target runtime (still local-first)

```
Agent
  └─ skill (read-only GitHub; commercial commands first; power-user appendix)
        └─ upstream CLIs (gh, yt-dlp, mcporter, curl jina, feedparser)
Agent-reach CLI
  ├─ install (check-only default; --system warned)
  ├─ doctor (honest statuses, still no cookie refresh)
  ├─ configure (keychain; stdin cookies for gated channels)
  └─ MCP get_status (unchanged)
Owned fetch
  └─ none, or DNS-pinned helpers only
```

Dashed exception path (Web/V2EX/Xueqiu) is either removed or pinned. That is the architecture change. Everything else is policy on top of existing glue.

## Surfaces we will not grow

- No `AgentReach.read(url)` public library API. Adding it would make AR a wrapper. `WebChannel.read` can stay private or move behind an explicit internal helper; do not export it from `core.py`.
- No extra MCP tools.
- No HTTP server.
- No QR flow.

## Trust boundary

Agent Reach runs as the same user as the agent. There is no remote AR service. Compromise model:

1. Agent with exec can already run anything the user can. AR's job is to not make that worse (no `--system` by default, no cookies in transcripts, no skill that teaches writes).
2. Shared host / SSRF-capable agent: in-process fetch + yt-dlp must not follow a hostname to `169.254.169.254`.
3. Cloud agent transcripts: session cookies in chat = account takeover. This is the highest-likelihood product bug. It is documentation + UX, not RCE.

## Versioning and packaging

Keep hatchling wheel (`pyproject.toml`). CI already has a wheel-gate that asserts `SKILL.md` ships. Phase 5 adds: constraints on the published install recipe, a real version assert in tests, changelog for 1.5.x / 1.6 product cut, and distribution that is not "pip install a zip from main".

## Upstream rule

Never modify twitter-cli, OpenCLI, gh, yt-dlp, Jina, Exa, xiaohongshu-mcp, etc. Route and constrain. If an upstream CLI cannot be used safely (cookie auto-refresh, write APIs), we wrap **our** invocation or we drop it from the commercial set. We do not patch their source.
