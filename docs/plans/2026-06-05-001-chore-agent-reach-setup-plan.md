---
title: "chore: Set up Agent-Reach with Twitter/X access on Windows"
type: chore
status: completed
date: 2026-06-05
---

# chore: Set up Agent-Reach with Twitter/X access on Windows

## Summary

Install Agent-Reach into an isolated Python virtual environment on this Windows
machine (pipx is absent, so a venv is the recommended path), run the auto
installer to activate the zero-config core channels, install `twitter-cli`,
configure Twitter/X cookie auth, and leave behind a reusable script that proves
X/Twitter fetching actually works. Scope is **Twitter/X + core channels** —
other platforms are deferred and can be added later with one command.

---

## Problem Frame

The user has cloned `github.com/Panniantong/Agent-Reach` and wants their AI agent
to have internet reach, with Twitter/X as the priority. Agent-Reach is an
installer + doctor + config tool: after install, the agent calls upstream tools
(`twitter`, `yt-dlp`, `gh`, Jina Reader, Exa via `mcporter`) directly. The
machine has Python 3.11, uv, Node 22, npm, gh, git, and ffmpeg, but **no pipx**,
so the package and `twitter-cli` need a venv. Raw `curl` is sandboxed in this
tool environment (returns `000`) while `pip` reaches PyPI fine — so runtime
network parity must be verified, not assumed.

---

## Requirements

### Installation

- R1. Agent-Reach CLI is installed and runnable from an isolated venv on Windows, without modifying system Python.
- R2. The zero-config core channels are active: Web (Jina Reader), YouTube, GitHub, RSS, Exa search, V2EX, and Bilibili (basic).

### Twitter/X

- R3. `twitter-cli` is installed and the `twitter` command is discoverable on PATH for the agent's invocations.
- R4. Twitter/X credentials (`auth_token`, `ct0`) are configured from a **dedicated/burner** account, stored locally only.
- R5. `twitter status` reports authenticated (`ok: true`) and a real fetch (search or read a tweet) returns live data.

### Verification & hygiene

- R6. `agent-reach doctor` runs and its full output is reviewed with the user.
- R7. A reusable verification script exists that the user or agent can run on demand to confirm X fetching works.
- R8. No changes are made to Agent-Reach source code or the upstream repo's git history; credentials live only in `~/.agent-reach/config.yaml`.

---

## Key Technical Decisions

- KTD1. **Virtual environment, not pipx.** pipx is not installed; the user's stated preference is "pipx if available, otherwise a venv." uv is present but a plain `venv` keeps the setup simple and matches both `docs/install.md` (PEP 668 fallback) and `CLAUDE.md`'s `pip install -e .` convention.
- KTD2. **venv lives outside the clone at `~/.agent-reach-venv`.** `.venv` is *not* in the repo's `.gitignore` (only `.agent-reach/`, `*.egg-info/`, `dist/`, `build/` are), so a repo-local venv would dirty the working tree. An external venv keeps `git status` clean and matches the doc's `~/.agent-reach-venv` convention.
- KTD3. **Editable install (`pip install -e .`) from the local clone.** Matches `CLAUDE.md`'s dev convention and lets future `git pull`s take effect without reinstalling.
- KTD4. **Install `twitter-cli` into the same venv via `pip`** (not `uv tool`/pipx). pipx is absent; a same-venv install puts `twitter.exe` in the venv `Scripts\` dir, so `shutil.which("twitter")` resolves it once that dir is on PATH — no reliance on a uv tools bin being on PATH. Pin observed at plan time: `twitter-cli 0.8.5`.
- KTD5. **Prepend the venv `Scripts\` dir to `PATH` per command; don't rely on activation.** PowerShell activation doesn't persist across separate tool calls, so each invocation explicitly prepends `Scripts\` and sets `PYTHONUTF8=1` for clean emoji/Chinese CLI output.
- KTD6. **Cookie auth via Cookie-Editor "Header String" (`auth_token` + `ct0`).** Per project rules (Cookie-Editor export only, never QR) and security guidance — use a dedicated account because cookie auth carries ban and credential-exposure risk.

---

## Implementation Units

Setup steps, dependency-ordered. Commands are the deliverable for this runbook
and are shown explicitly so they can be reviewed before execution. PowerShell is
the primary shell; `$VENV = "$env:USERPROFILE\.agent-reach-venv"` and
`$SCRIPTS = "$VENV\Scripts"` are assumed set.

### U1. Create the Python virtual environment

- Goal: An isolated interpreter at `~/.agent-reach-venv` with up-to-date pip.
- Requirements: R1
- Dependencies: none
- Commands:
  ```powershell
  $env:PYTHONUTF8 = "1"
  $VENV = "$env:USERPROFILE\.agent-reach-venv"
  python -m venv $VENV
  & "$VENV\Scripts\python.exe" -m pip install --upgrade pip
  ```
- Verification: `& "$VENV\Scripts\python.exe" --version` prints 3.11.x; `pip --version` points inside `$VENV`.

### U2. Install Agent-Reach (editable) into the venv

- Goal: `agent-reach` console script available in the venv from the local clone.
- Requirements: R1
- Dependencies: U1
- Files: `C:\dev\Agent-Reach\pyproject.toml` (source of the install; not modified)
- Commands:
  ```powershell
  & "$VENV\Scripts\python.exe" -m pip install -e C:\dev\Agent-Reach
  ```
- Verification: `& "$VENV\Scripts\agent-reach.exe" --version` prints `Agent Reach v1.4.0`.

### U3. Run the auto installer

- Goal: Activate zero-config core channels; install/configure mcporter + Exa, gh check, yt-dlp JS runtime; register SKILL.md.
- Requirements: R2
- Dependencies: U2
- Approach: Run with the venv `Scripts\` prepended to PATH so `node`/`npm`/`gh` (already on PATH) and the venv tools are all visible. `--env=auto` will detect "local".
  ```powershell
  $env:PATH = "$SCRIPTS;$env:PATH"; $env:PYTHONUTF8 = "1"
  agent-reach install --env=auto
  ```
- Notes: `mcporter` install (npm global) and Exa registration need network via Node; on a restricted network these may warn — non-blocking for the Twitter goal. No `--channels` passed, so no cookie auto-import is triggered at this step.
- Verification: Installer prints "Installation complete! N/total channels active" and a report table; core channels (web, youtube, github, rss, v2ex) show ✅.

### U4. Install twitter-cli into the venv

- Goal: `twitter` command present and detectable.
- Requirements: R3
- Dependencies: U2
- Commands:
  ```powershell
  & "$VENV\Scripts\python.exe" -m pip install twitter-cli
  ```
- Verification: `& "$SCRIPTS\twitter.exe" --help` runs; with `$env:PATH` prepended, `(Get-Command twitter).Source` resolves into `$SCRIPTS`.

### U5. Run doctor and review full output

- Goal: Capture the complete channel-status report and surface anything broken.
- Requirements: R6
- Dependencies: U3, U4
- Commands:
  ```powershell
  $env:PATH = "$SCRIPTS;$env:PATH"; $env:PYTHONUTF8 = "1"
  agent-reach doctor
  ```
- Expected: Twitter shows ⚠️ "installed but not authenticated" until U6 supplies cookies. Core channels green. Any ❌/⚠️ on mcporter/Exa/gh is noted and explained (likely network or auth), not necessarily fixed if outside the Twitter scope.
- Verification: Full doctor output shown to the user.

### U6. Configure Twitter/X cookies

- Goal: Store `auth_token` + `ct0` and confirm twitter-cli authenticates.
- Requirements: R4
- Dependencies: U4
- **User input required:** From a logged-in **dedicated/burner** X account, export cookies with the Cookie-Editor extension (icon → Export → **Header String**) and paste the string.
- Commands (the agent runs, given the pasted string):
  ```powershell
  $env:PATH = "$SCRIPTS;$env:PATH"
  agent-reach configure twitter-cookies "<pasted header string with auth_token=...; ct0=...>"
  ```
- Approach: `_cmd_configure` parses `auth_token`/`ct0` out of the header string, writes them to `~/.agent-reach/config.yaml`, sets `TWITTER_AUTH_TOKEN`/`TWITTER_CT0` for a probe subprocess, and runs `twitter status`.
- Verification: Command prints "✅ Twitter cookies configured!" then "✅ Twitter access works!" (i.e. `twitter status` returned `ok: true`).

### U7. Create and run the X/Twitter verification script

- Goal: A reusable, self-contained script that proves live fetching, independent of the install session.
- Requirements: R5, R7
- Dependencies: U6
- Files: `C:\dev\Agent-Reach\scripts\verify_twitter.ps1` (new, local-only helper)
- Approach: The script reads `auth_token`/`ct0` from `~/.agent-reach/config.yaml`, exports them as `TWITTER_AUTH_TOKEN`/`TWITTER_CT0` (twitter-cli reads these directly — Agent-Reach is not a wrapper), puts the venv `Scripts\` on PATH, then runs `twitter status` followed by a real `twitter search` (and optionally `twitter tweet <URL>`), printing PASS/FAIL.
- Test scenarios:
  - Authenticated status: `twitter status` output contains `ok: true` → PASS.
  - Live search: `twitter search "openai" -n 3` returns ≥1 tweet → PASS.
  - Missing/invalid cookies: script reports a clear FAIL with the remediation hint (re-run U6) rather than a raw stack trace.
  - Network blocked: a fetch error is surfaced as FAIL with a note to retry in the user's own shell via the `! <command>` prefix.
- Verification: Running `powershell -File scripts\verify_twitter.ps1` prints PASS for status and search and shows sample tweet text.

---

## Risks & Dependencies

- **Runtime network parity.** Raw `curl` is sandboxed here (`000`), though `pip` reaches PyPI. `twitter-cli` is Python and should have pip-level network access, but this is unverified until U7. If Python network is also restricted in this tool sandbox, doctor/twitter will warn — mitigation: have the user run the verification (or the raw `twitter` commands) in their own shell via the `! <command>` prefix.
- **Cookie validity / account safety.** Cookies expire or get invalidated; scripted access risks account limits. Mitigation: dedicated burner account (KTD6); re-export via Cookie-Editor when `twitter status` stops returning `ok: true`.
- **mcporter / Exa / gh need network too** (Node fetch / GitHub API). On a restricted network these channels may warn in doctor; non-blocking for the Twitter-focused goal.
- **Upstream churn.** `twitter-cli` (pinned `0.8.5` at plan time) could change its cookie scheme or CLI surface; the doctor check keys on `twitter status` → `ok: true`.
- **Blocking dependency:** U6 cannot complete without the user pasting cookies; R4/R5 are gated on it.

---

## Scope Boundaries

### Deferred to follow-up (addable later, no rework)

- Reddit, Weibo, WeChat, XiaoHongShu, Douyin, LinkedIn, Xueqiu, Xiaoyuzhou, full Bilibili — each addable via `agent-reach install --env=auto --channels=<name>` plus its own auth where needed.

### Out of scope

- Residential proxy setup (only needed for server IP blocks; this is a local machine).
- OpenClaw daily-cron monitoring (`agent-reach watch`).
- Any modification of Agent-Reach source or a PR to the upstream repo.

---

## Sources / Research

- `docs/install.md` — install flow, channel names, `configure twitter-cookies` usage, Cookie-Editor method.
- `docs/cookie-export.md` — Cookie-Editor "Header String" export steps for x.com.
- `agent_reach/cli.py` — `_cmd_install` / `_detect_environment` (install + auto env detect), `_install_twitter_deps` (pipx/uv installer for `twitter-cli`), `_cmd_configure` + `_parse_twitter_cookie_input` (cookie parsing → `config.yaml` + `twitter status` probe).
- `agent_reach/channels/twitter.py` — `check()` expects `twitter status` to print `ok: true`; reads `TWITTER_AUTH_TOKEN` / `TWITTER_CT0`.
- `agent_reach/config.py` — config at `~/.agent-reach/config.yaml`; `get()` also resolves the uppercase env-var form of a key.
- Environment probe (this session): Python 3.11.9, uv 0.11.3, Node 22.13.1, npm 10.9.2, gh 2.87.0, ffmpeg 7.1.1 present; pipx absent; `twitter-cli` latest 0.8.5 on PyPI.
