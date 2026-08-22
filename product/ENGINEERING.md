# Engineering — convert without breaking CLI users

This is the playbook for Phases 1–5. Phase 0 does not touch production code.

## Compatibility contract

Existing users run:

```
agent-reach install --env=auto
agent-reach install --env=auto --system
agent-reach doctor
agent-reach doctor --json
agent-reach configure <key>
agent-reach configure twitter-cookies --stdin
agent-reach uninstall
agent-reach skill --install
agent-reach transcribe <url>
agent-reach check-update
agent-reach version
```

**Do not** rename these, remove flags, or change exit codes without Pepe's approval.

Safe to add: extra JSON fields (if approved), extra warnings on stderr, new subcommands (`agent-reach gh`), new docs.

Unsafe without asking: new required flags, `--system` requiring a second flag, doctor `status` enum values beyond `ok|warn|off|error`, deleting configure keys, changing `~/.agent-reach/config.yaml` schema in a way that drops keys.

## Conversion strategy

1. **Tell the truth in docs** (Phase 1) while behavior stays.
2. **Harden** (Phase 2) with tests that lock the new policy.
3. **Move secrets** (Phase 3) with a migrate-from path so old YAML still loads.
4. **Gate product vs power-user** (Phase 4) in skill + install hints, not by deleting channels.
5. **Release** (Phase 5) on a branch, PR to main, tag. Never push to main.

Smallest viable change. Match existing patterns (`probe.py`, `Config` 0600 writes, channel `check()` returning `(status, message)`). Do not add runtime deps unless Phase 3's keychain pick requires it.

## Doctor JSON (today)

`doctor.py:check_all` returns per channel:

```
name, status, message, tier, backends, active_backend
```

`status` in `{ok, warn, off, error}` (`test_channel_contracts.py`).

Proposed additive field (F3.2, **blocked** for Phase 1 execute, ADR-017):

```
confidence: "live" | "configured" | "installed" | "missing"
```

Mapping without running forbidden probes:

| Channel example | status (keep) | confidence (add) |
|-----------------|---------------|------------------|
| web always | ok | live (no probe needed) |
| youtube yt-dlp works | ok | live |
| gh present + hosts.yml | warn | configured |
| gh present, no auth | warn | installed |
| twitter cookies in config, no status probe | warn | configured |
| mcporter + exa in config | warn | configured |
| missing binary | off/warn as today | missing |

If Pepe rejects the field, only skill/report prose changes. Do not remap `warn` → `ok` for github/twitter. That would look like a live probe we did not do.

## Skill changes without breaking routing

Agents already exec upstream. Skill edits are the highest-leverage behavior change and do not require Python API changes.

Phase 1–4 skill rules:

- Keep the routing table and reference files.
- Remove cookie-paste and "用户只需提供 cookies".
- Remove unsolicited `check-update` (Phase 1, ADR-017 YES).
- Put commercial commands in the zero-config block; move OpenCLI/cookie commands under a power-user heading.
- Replace `dev.md` writes with reads; point writes at "not enabled by Agent Reach".
- Dual-language: `SKILL.md` and `SKILL_en.md` (`cli.py:479-488` locale pick). Change both.

Skill copies land in four trees only when `--system` or `skill --install` runs. Doc-only skill edits in the package do not update already-copied skills until reinstall. Mention that in the Phase 1 PR.

## Install path

Keep:

```
safe_mode = getattr(args, "safe", False) or not getattr(args, "system", False)
```

Phase 1 docs: the copy-paste block is `install --env=auto` only.

Phase 2 CLI: when `--system` is set, print:

- Will copy skill into whichever of `~/.claude/skills`, `~/.openclaw/skills`, `~/.config/opencode/skills`, `~/.agents/skills` exist (and may create `~/.agents/skills/agent-reach` if none exist).
- May apt-get/brew/npm gh, nodejs, npm.
- May write mcporter config.

Do not add `--i-understand-system` unless Pepe says yes.

Default `--channels` empty: do not auto-install twitter/xhs. That is already the case (`cli.py:450-455` hints after `--system`). Phase 4: make the hint commercial-first.

## Constraints on user install

Today:

```
pip install https://github.com/Panniantong/agent-reach/archive/main.zip
```

Phase 1:

```
pip install -c constraints.txt <same url or sdist>
```

For a zip from GitHub, `constraints.txt` must be fetched too (it is in the zip). pipx from a zip cannot easily take `-c`. Document: clone or `curl` constraints, or `pip install -c https://raw.githubusercontent.com/.../constraints.txt`. Wheel-gate already exists; keep it.

Do not pin `pyproject.toml` ranges without asking.

## Secrets migration (Phase 3)

Algorithm:

1. `configure` writes keychain; also writes YAML only if `AGENT_REACH_SECRETS=yaml` (or until migration complete: write both, prefer keychain on read).
2. `Config.get` for sensitive keys: keychain → YAML → env (env already uppercase fallback, `config.py:159-168`).
3. `uninstall` deletes keychain items we created, plus `~/.agent-reach/`.
4. Tests use an in-memory backend.

Sensitive key names already used by `to_dict()` markers: key, token, password, proxy, cookie, secret, session, sessdata, csrf, auth, cred, ct0.

Service name (proposed, confirm at implement): `agent-reach`. Account: the config key (`twitter_auth_token`, `github_token`, …).

Twitter ADR-004 A: wrapper `agent-reach twitter -- search ...` that execs `twitter` with `twitter_cli_child_env` + keychain. Agent skill uses the wrapper. PATH `twitter` still works if the user exported env themselves.

Twitter ADR-004 B: `configure twitter-cookies` refuses to save; prints "export TWITTER_AUTH_TOKEN=... in the twitter process only". Doctor checks env, not YAML.

## GitHub wrapper (Phase 4)

Proposed: `agent-reach gh -- <args>` allowlist.

Allow: `search`, `repo view`, `repo list`, `issue list`, `issue view`, `pr list`, `pr view`, `pr checks`, `api` with GET-only methods, `auth status` (user-invoked, not doctor), `run list`, `run view`, `workflow list`, `release list`.

Deny: `issue create`, `pr create`, `pr merge`, `repo create`, `repo fork`, `repo delete`, `release create`, `api` POST/PATCH/PUT/DELETE.

Implementation: parse argv, fail closed on unknown verbs. Exec `gh` with the same telemetry-off env doctor uses. Do not install a `gh` shim on PATH.

Skill `dev.md` only shows the wrapper. Advanced users still have real `gh`.

## SSRF helper (Phase 2)

Add `utils/url.py` function used by web, v2ex, xueqiu, transcribe:

1. Existing `normalize_public_http_url` (literals + denylist).
2. `getaddrinfo` the host.
3. Every A/AAAA must be global unicast (`ipaddress`: not private, loopback, link-local, reserved, multicast, unspecified, not documentation).
4. Fail closed if any address is bad (prevents happy-eyeballs to metadata).
5. Either pass the original URL to upstream **after** pin check (TOCTOU remains unless we connect ourselves) or connect with `ssl` to the pinned IP using original SNI/Host.

Honest limitation: if we still hand a hostname to yt-dlp/Jina after a successful resolve, DNS can change. Product bar is: pin on **our** fetchers; for yt-dlp, re-resolve immediately before exec and/or pass IP with Host header if yt-dlp allows. If not, document residual TOCTOU and still reject obvious bad first-hop DNS.

Tests: fake `getaddrinfo`.

## What not to touch

- Upstream OSS checkouts.
- `tests/test_doctor_credential_boundaries.py` assertions (extend, do not loosen).
- `shell=True`.
- Enabling `--from-browser` for twitter/xhs.
- Exporting `AgentReach.read`.
- MCP tool list.

## Version bump procedure (Phase 5, also any interim)

1. `pyproject.toml` `version`
2. `agent_reach/__init__.py` `__version__`
3. Test that compares the two (Phase 1 adds this; bump both together)
4. `CHANGELOG.md`
5. Branch + PR. Pepe tags.

CLAUDE.md currently lists `tests/test_cli.py` as the third place. Either put the assert there or change CLAUDE.md to name the actual test module. Do not leave a third place that does not assert.

## PR shape per phase

One phase = one PR unless the phase is too large (then split by ADR, still on one branch). Commit format `type(scope): message`. Pepe asks for commits; do not commit unprompted.

Suggested Phase 1 PR title: `docs(product): align contract, pins, and doctor honesty`

No `--no-verify`. `pytest tests/ -v` green.

## Root README pointer

Skipped in Phase 0. README is a marketing homepage with language links, not a docs index. Phase 1: add one line under 设计理念 or a small "Productization" link to `product/README.md` (ADR-017 YES).
