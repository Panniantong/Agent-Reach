# Directory layout — current vs target

Phase 0 adds `product/` only. Do not restructure `agent_reach/` until a later phase needs a file. Prefer new files over moving old ones.

## Current (v1.5.0, inspected)

```
Agent-Reach/
  agent_reach/
    __init__.py              # __version__ = "1.5.0"
    cli.py                   # argparse: install, doctor, configure, skill, transcribe, …
    core.py                  # AgentReach.doctor() only; not a router
    config.py                # ~/.agent-reach/config.yaml, 0600, symlink-safe
    doctor.py                # check_all → format_report
    cookie_extract.py        # browser-cookie3 path; twitter/xhs blocked
    probe.py                 # argv probes, no shell=True
    transcribe.py            # yt-dlp + Whisper; literal-IP SSRF only
    channels/
      __init__.py            # ALL_CHANNELS: 15
      base.py                # can_handle + check
      github.py twitter.py youtube.py reddit.py facebook.py instagram.py
      bilibili.py xiaohongshu.py linkedin.py xiaoyuzhou.py v2ex.py
      xueqiu.py rss.py exa_search.py web.py
      _opencli_site.py mcporter.py
    backends/opencli.py
    integrations/mcp_server.py   # get_status, read-only config
    skill/SKILL.md + SKILL_en.md + references/{search,social,career,dev,web,video,finance}.md
    guides/setup-*.md
    scripts/transcribe_xiaoyuzhou.sh
    utils/{paths,url,text,process}.py
  tests/                     # 33 modules (plus conftest)
  docs/                      # install, update, cookie-export, translations, sponsors
  config/mcporter.json
  product/                   # this workspace (Phase 0)
    README.md PRD.md ARCHITECTURE.md SECURITY.md ROADMAP.md
    DIRECTORY.md SCOPE.md DECISIONS.md CHANNELS.md ENGINEERING.md
    FEATURES.md CHECKLIST.md NEW-CHAT-PROMPT.md
    features/F01-contract-truth.md … F12-telemetry-update.md
  pyproject.toml             # version 1.5.0, unpinned runtime ranges
  constraints.txt            # used by CI, not default user install
  CLAUDE.md README.md SECURITY.md CONTRIBUTING.md CHANGELOG.md LICENSE
  test.sh .env.example
  .github/workflows/pytest.yml
  scripts/sync-upstream.sh
```

Not a product layout problem. The catalog is already one-file-per-channel. The productization gap is policy, secrets, docs, and a few owned fetchers.

## Target (end of Phase 5)

Keep the current tree. Add, do not rearrange:

```
Agent-Reach/
  agent_reach/                 # unchanged shape
    secrets.py                 # NEW Phase 3: keychain backend (or secrets/)
    policy/                    # NEW Phase 4 if wrapper lands here
      gh_readonly.py           # allowlist exec of gh
    utils/
      url.py                   # EXTEND Phase 2: DNS-pin helper
  product/                     # THIS dir. Lives for the life of the conversion.
    README.md PRD.md ARCHITECTURE.md SECURITY.md ROADMAP.md
    DIRECTORY.md SCOPE.md DECISIONS.md CHANNELS.md ENGINEERING.md
    FEATURES.md CHECKLIST.md NEW-CHAT-PROMPT.md
    features/F01 … F12
  docs/
    install.md                 # constraints + check-only + --system blast radius
    cookie-export.md           # stdin only (Phase 2)
  constraints.txt              # default install path (Phase 1)
  tests/
    test_docs_contract.py      # NEW Phase 1: version, channel count, no cookie-paste
    test_dns_pin.py            # NEW Phase 2
    test_gh_readonly.py        # NEW Phase 4
    test_secrets.py            # NEW Phase 3
```

## What we will not do

- Do not invent `src/` or split the package.
- Do not move channels into plugins for Phase 1–5.
- Do not bury this plan under `docs/`. `product/` at repo root is the workspace Pepe asked for.
- Do not delete `docs/` translations as part of productization. Phase 1 README/English claims should not drift from `docs/README_en.md` forever; sync in the same PR if we touch README.

## Runtime home directory (user machine)

Unchanged:

| Path | Role |
|------|------|
| `~/.agent-reach/config.yaml` | Config + (today) secrets. Phase 3: migrate-from. |
| `~/.agent-reach/tools/` | Upstream tool checkouts (`docs/install.md`) |
| `~/.claude/skills/agent-reach/` | Skill copy (`--system` / `skill --install`) |
| `~/.openclaw/skills/agent-reach/` | same |
| `~/.config/opencode/skills/agent-reach/` | same |
| `~/.agents/skills/agent-reach/` | same; fallback if no other skill root exists (`cli.py:569-572`) |
| `~/.config/gh/hosts.yml` | gh creds; doctor reads, does not run `gh auth status` |
| `~/.config/xfetch/session.json` | only if `--sync-legacy-twitter` |
| `~/.config/bird/credentials.env` | only if `--sync-legacy-twitter` |

Phase 3 adds OS keychain items under a service name like `agent-reach`. Document the exact service/account names in `ENGINEERING.md` when implementing.

## MCP config

`config/mcporter.json` in the repo is a template. User scope is mcporter home config (`exa_search.py` / `linkedin.py` inspect that). Do not put cookies in repo JSON.

## Tests map (security-relevant, keep)

| Module | Guards |
|--------|--------|
| `test_private_file_writes.py` | symlink-safe writes |
| `test_url_security.py` | host_matches, lookalikes |
| `test_scrub_credentials.py` | doctor output |
| `test_doctor_credential_boundaries.py` | no cookie refresh |
| `test_cookie_security.py` / `test_cookie_extract_perms.py` | extract policy |
| `test_mcp_server.py` | status-only |
| `test_channel_contracts.py` | registry shape |
| `test_paths.py` / `test_home_isolation.py` | HOME isolation |

Add, do not weaken.
