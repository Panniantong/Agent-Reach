# Security remediations

Source of findings: [Agent Reach security audit](/Users/pepe/.cursor/projects/Users-pepe-Development-Agent-Reach/canvases/agent-reach-security-audit.canvas.tsx) (agent 01e8e2f3-0dab-4f8b-95c1-31a55f4c5049), 2026-08-13, v1.5.0.

Do not re-litigate. Implement. Owner is engineering unless noted. Pepe approves any public API, auth, dependency, or skill-policy change before the phase starts.

Legend: **glue** = our code/docs. **inherent** = upstream/ToS/session model. **ops** = how the product is used.

## Summary

| ID | Sev | Kind | Phase | Remediation (short) |
|----|-----|------|-------|---------------------|
| cookie-agent-logs | high | ops | 2 | Kill cookie-in-chat docs. Stdin/getpass only. |
| agent-system-writes | high | glue | 2 | `--system` blast-radius docs; never default one-liner. |
| dns-rebinding | high | glue | 2 | DNS-pin or stop in-process fetch. |
| github-writes | high | inherent | 4 | Read-only skill + enforce `gh`. |
| twitter-dead-config | medium | glue | 3 | Inject child env or stop storing tokens. |
| doctor-false-neg | medium | glue | 1 | Honest statuses without cookie-refresh probes. |
| owned-fetchers | medium | glue | 2 | Pin or move Web/V2EX/Xueqiu fetch. |
| plaintext-secrets | medium | glue | 3 | OS keychain as product path. |
| unpinned-deps | medium | glue | 1 | `constraints.txt` on default install. |
| cookie-extract-scope | medium | inherent | 4 | Gate `--from-browser`; keep Twitter/XHS blocked. |
| xhs-header-flags | medium | glue | 2 | Stop weakening header-string cookie flags. |
| check-update-nudge | low | ops | 1 | Make check-update opt-in in the skill. |
| contract-drift | low | glue | 1 | 15 channels, real contract, version assert. |
| rss-substring | low | glue | 2 | Use `host_matches` or stop matching. |

## Already solid (do not regress)

These are controls to keep. Tests exist. Phase work must not weaken them.

| Control | Where | Tests |
|---------|-------|-------|
| Default install does not mutate the system | `cli.py:261` `safe_mode` | CLI install tests |
| No `shell=True`; probes are argv lists | `probe.py:47+` | `tests/test_probe.py` |
| Private writes refuse symlink components | `utils/paths.py`, `config.py:46-79` | `tests/test_private_file_writes.py` |
| Doctor will not run cookie-refreshing CLIs | twitter/github/xhs/reddit/opencli checks | `tests/test_doctor_credential_boundaries.py` |
| Host lookalikes and userinfo rejected | `utils/url.py:99-121` | `tests/test_url_security.py` |
| URL userinfo/query secrets scrubbed in doctor | `utils/text.py`, `doctor.py:36` | `tests/test_scrub_credentials.py` |
| Logging off unless `--verbose` | `cli.py:51-56` | |
| MCP is status-only, config read-only | `integrations/mcp_server.py:40-55` | `tests/test_mcp_server.py` |
| Twitter/XHS cannot `--from-browser` | `cli.py:190-194` | `tests/test_cookie_security.py` |
| Config `to_dict()` redacts token/cookie/key names | `config.py:211-233` | `tests/test_config.py` |
| Doctor warns if config.yaml is group/other readable | `doctor.py:114-127` | |

## Finding-by-finding plan

### cookie-agent-logs (high, ops) — Phase 2

**Evidence.** `docs/cookie-export.md:17-27` tells the user to paste Cookie-Editor output to the agent. `skill/SKILL.md:142`: "用户只需提供 cookies". Hidden CLI prompts exist (`configure` getpass / `--stdin`, `cli.py:106-110`).

**Impact.** Full account takeover of Twitter/XHS if the conversation is stored, synced, or leaked.

**Fix.** Rewrite cookie-export, install, skill, and guides so the only documented path is: export locally, pipe to `agent-reach configure twitter-cookies --stdin` (or interactive getpass on a local TTY). Add a regression test that greps skill + docs for "paste" / "Here are my Twitter cookies". Positional secret args already warn; keep warning, prefer removing positional secrets in Phase 2 if Pepe approves a small CLI help-text change (not a flag rename).

**Do not.** Disable configure. Do not add QR.

### agent-system-writes (high, glue) — Phase 2 (docs in Phase 1)

**Evidence.** Default is check-only (`cli.py:254-261`). `--system` copies SKILL.md into `~/.claude/skills`, `~/.openclaw/skills`, `~/.config/opencode/skills`, `~/.agents/skills` (`cli.py:541-547`) and can apt-get/brew/npm (`cli.py:697-752`).

**Impact.** An agent with exec, told to "install Agent Reach", can persist instructions into other agents and install global tools.

**Fix.** Phase 1: README / `docs/install.md` copy-paste is check-only only; `--system` sits behind an explicit "blast radius" section (skill dirs + OS packages). Phase 2: print that blast radius from the CLI when `--system` is passed, require a second confirmation or `--i-understand-system` only if Pepe approves a flag add (that is a public API change: **ask first**). Default stays check-only either way.

### dns-rebinding (high, glue) — Phase 2

**Evidence.** `utils/url.py:47-84` and `transcribe.py:214-247` reject private **literal** IPs and a small host denylist, then skip DNS. `web.py:48-67` prefixes the URL onto `r.jina.ai`. `transcribe.py:250-270` hands the URL to yt-dlp after that check.

**Impact.** A hostname that later resolves to `169.254.169.254` or loopback can still be fetched by Jina or yt-dlp.

**Fix.** Shared helper: resolve DNS, pin to global unicast, reconnect to that IP with TLS name intact (or fail closed). Apply to `normalize_public_http_url`, transcribe, V2EX, Xueqiu. Tests with a fake resolver. Alternative Pepe can pick: delete `WebChannel.read` and V2EX/Xueqiu in-process clients; skill uses `curl` only (moves SSRF to curl, which still needs a pinned wrapper if we care on shared hosts).

**Approve.** Mechanism (pin vs stop fetching). New helper is internal, not a public API, unless we export it.

### github-writes (high, inherent) — Phase 4

**Evidence.** README platform table unlocks private repos, issues, PRs, forks via `gh`. `SKILL.md:17-18` forbids posts/likes, not `gh` writes. `skill/references/dev.md:21-45` documents `gh repo create`, `fork`, `issue create`, `pr create`, `release create`. After install, agents call `gh` directly (`core.py:6-8`).

**Fix.** Rewrite `dev.md` to read-only commands. Add an allowlist wrapper or `agent-reach gh --read-only` that execs `gh` with a verb allowlist. Skill tells the agent to use the wrapper. Do not silently replace `gh` on PATH.

**Approve.** Wrapper vs skill-only. Wrapper is the product bar ("enforced where possible"). Skill-only is a Phase 4 half-measure.

### twitter-dead-config (medium, glue) — Phase 3

**Evidence.** Configure writes `twitter_auth_token` / `twitter_ct0` to YAML. Doctor refuses `twitter status` (`twitter.py:83-109`) because upstream auto-reads browser cookies. `twitter_cli_child_env` (`twitter.py:12-31`) can inject saved creds into a **child** env and is tested (`tests/test_twitter_channel.py`), but no production spawn uses it. `SKILL.md:81-84` tells the agent to set `TWITTER_AUTH_TOKEN` / `TWITTER_CT0` in the process env.

**Fix.** Pick one: (A) document and use child-env injection from keychain/YAML when the agent runs `twitter` via a tiny wrapper; (B) stop storing Twitter tokens in AR config; doctor only checks env. Do not do both poorly.

**Approve.** A vs B. A is a thin wrapper (policy). B is less surface.

### doctor-false-neg (medium, glue) — Phase 1

**Evidence.** twitter, github, xiaohongshu, reddit, `_opencli_site`, exa_search, linkedin all return `warn` even when tools look installed, to avoid cookie refresh / telemetry / live MCP. SKILL says follow `active_backend`; those channels leave it null. 7 channels can return `ok` (web, youtube, rss, bilibili, v2ex, xueqiu, xiaoyuzhou); 8 never do.

**Fix without weakening cookie-refresh refusal.** Phase 1 (F3.1, ADR-017): prose in `format_report` + skill. Do **not** add a JSON field this phase. F3.2 (`confidence: live | configured | installed | missing`) stays blocked as a public API change. Keep `status=warn` for compatibility. Skill text already says `active_backend: null` is not proof of absence (`SKILL.md:32-35`). Make that obvious in the text report.

**Approve.** New JSON field is a public API change for `doctor --json`. Encoded NO for Phase 1 execute (ADR-017). Ask again before shipping F3.2.

### owned-fetchers (medium, glue) — Phase 2

**Evidence.** `web.py:48-67`, `v2ex.py` public API + curl TLS fallback, `xueqiu.py` cookie jar + stock APIs. RSS skill imports feedparser; `rss.py` never parses.

**Fix.** Same as dns-rebinding. Prefer skill-side curl/feedparser. If we keep Python fetchers, they go through the DNS-pin helper. Xueqiu process-global `CookieJar` (`xueqiu.py:24-28`) is power-user; do not make it the product path.

### plaintext-secrets (medium, glue) — Phase 3

**Evidence.** `config.py:99-103, 46-79, 211-233`: `~/.agent-reach/config.yaml`, atomic write, `fchmod 0600`, `to_dict` redacts. `cookie_extract.py` can also write `~/.config/xfetch/session.json` and `~/.config/bird/credentials.env` if `--sync-legacy-twitter`.

**Fix.** Product path: macOS Keychain / libsecret / Windows Credential Manager. YAML remains a migrate-from store, not the happy path. Do not add a runtime dep without Pepe's approval (keyring would be one). Alternative: wrap `security` / `secret-tool` CLIs to avoid a Python dep.

**Approve.** `keyring` extra vs OS CLI wrappers. This is a dependency decision.

### unpinned-deps (medium, glue) — Phase 1

**Evidence.** `pyproject.toml:30-37` uses `>=` pins. `constraints.txt` exists. CI uses it. Default git/zip install (`docs/install.md:53-62`) does not.

**Fix.** Change install recipes to `pip install -c constraints.txt ...`. Document in `docs/install.md` and `docs/dependency-locking.md`. Do not freeze ranges inside `pyproject.toml` without Pepe (that's a dep policy change); pinning via constraints on the documented path is enough for Phase 1.

### cookie-extract-scope (medium, inherent) — Phase 4

**Evidence.** `cookie_extract.py:198-207` blocks Twitter/XHS auto-extract. `configure --from-browser` still works for xueqiu and bilibili.

**Fix.** Keep Twitter/XHS blocked. Gate `--from-browser` behind power-user docs. Consider requiring an extra flag later. Do not expand browser decryption.

### xhs-header-flags (medium, glue) — Phase 2

**Evidence.** JSON Cookie-Editor path domain-filters (`cli.py:1614-1638`). Header-string path (`cli.py:1668-1690`) forces domain `.xiaohongshu.com` but sets `httpOnly:false`, `secure:false`, then docker cp + docker restart (`cli.py:1753-1787`).

**Fix.** Set `secure:true` and `httpOnly:true` on the synthesized cookies unless the upstream MCP requires otherwise. Document Docker socket blast radius. Tests for flag values.

### check-update-nudge (low, ops) — Phase 1

**Evidence.** `SKILL.md:39-42` tells agents to hit GitHub after research tasks. `cli.py:2222-2281` GETs `api.github.com/repos/Panniantong/Agent-Reach`. `github.py:20-27` disables gh telemetry on doctor probes.

**Fix.** Remove the "after every large task" instruction. Keep `check-update` as a user-invoked command. Optional: only run if `config.check_update_on_skill` is true (that is a config key add: ask).

### contract-drift (low, glue) — Phase 1

**Evidence.** CLAUDE.md: 13 platforms, `read`/`search` required. `channels/__init__.py` registers 15. `base.py` requires `can_handle` + `check`. `tests/test_cli.py` never asserts `__version__ == 1.5.0`. `pyproject.toml:4` "entire internet" / "10+ platforms". `docs/install.md:42` says `config.json`; actual file is `config.yaml`.

**Fix.** Align CLAUDE.md, README claims, pyproject description, CONTRIBUTING.md ("update doctor.py" is wrong; registry auto-discovers), install.md. Add `assert __version__ == version in pyproject`. Channel count test already unique-names; add `len(get_all_channels()) == 15` if not present.

### rss-substring (low, glue) — Phase 2

**Evidence.** `rss.py:13-14` substring match. Unused by core (no router). Becomes a bug if someone later fetches behind `can_handle`.

**Fix.** Switch to feed-URL heuristics that still are not host-lookalike-safe, or document "unused matcher" and add a test that core does not route on it. Prefer tightening the matcher while it is still unused.

## Test gaps to add (by phase)

Phase 1: version three-place assert; docs/skill grep that channel count is 15 in CLAUDE.md; install.md uses `-c constraints.txt`; no cookie-paste one-liner in skill; no `[mcp]` extra lie in mcp_server.py.

Phase 2: DNS-pin unit tests; cookie-paste phrase grep; xhs header flags; `--system` prints blast radius.

Phase 3: keychain round-trip; twitter env injection **or** configure-refuses-to-store.

Phase 4: gh wrapper allowlist (create/fork rejected); `--from-browser` still blocked for twitter/xhs.

Phase 5: wheel still ships skill; constraints used in published recipe.

## What we will not do

- Host cookies.
- Weaken `test_doctor_credential_boundaries.py`.
- Enable `shell=True`.
- Follow symlinks into credential files.
- Make `--system` the default.
