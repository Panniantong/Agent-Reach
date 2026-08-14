# Decisions (ADRs)

Frozen unless Pepe reopens. Date: 2026-08-13. Basis: security audit + repo inspection.

---

## ADR-001 — Local-first, not hosted

**Decision.** Agent Reach runs on the user's machine (or their own VPS). There is no Agent Reach cloud that holds user sessions.

**Why.** No tenancy, plaintext cookies, agents exec upstream with user credentials. Hosting other people's cookies is account takeover as a service.

**Consequences.** Distribution is pip/pipx/git. MCP is stdio. Doctor is local. Support story is "run doctor", not "check our dashboard".

**Revisit if.** Pepe wants a hosted **keyless** commercial subset (Jina + Exa + public gh) with **user-supplied** tokens in the user's runtime only. Still no cookie hosting.

---

## ADR-002 — Do not productize as a cookie SaaS

**Decision.** Cookie/OpenCLI platforms are power-user optional, burner-only. They are not the product.

**Why.** Audit verdict. ToS of X / XHS / Reddit / LinkedIn. Ban risk the README already admits. Session cookies in agent logs.

**Consequences.** Commercial marketing and default install talk about GitHub + Exa + YouTube + RSS/Jina. Cookie docs are a gated appendix. QR login stays forbidden.

---

## ADR-003 — Read-only is enforced for GitHub, not just written in the skill

**Decision.** Default skill must not teach `gh` writes. Phase 4 adds a wrapper or allowlist so "enforced where possible" is real.

**Why.** `SKILL.md` already forbids posts/likes. It does not forbid `gh issue create`. After install, agents call `gh` directly. Skill prose is not a security boundary.

**Consequences.** Need Pepe's pick: `agent-reach gh` wrapper vs a shell wrapper installed next to the skill vs skill-only (accepted exception). Default recommendation: wrapper invoked by the skill, `gh` on PATH left intact.

**Out.** Silently replacing `gh` on PATH.

---

## ADR-004 — Twitter tokens: inject or stop storing (pick in Phase 3)

**Decision (direction).** The current path is a lie: YAML stores `twitter_auth_token`/`twitter_ct0`; `twitter` does not read them; skill tells the agent to export env vars; `twitter_cli_child_env` exists but is unused for spawn.

**Options (Pepe picks in Phase 3).**

- **A.** Thin wrapper that execs `twitter` with child env from keychain. Doctor still does not run `twitter status`.
- **B.** Stop persisting Twitter cookies in AR config. Configure becomes a check that the env is set, or a one-shot that prints export instructions without storing.

**Interim.** Do not add more stores (`--sync-legacy-twitter` stays explicit).

---

## ADR-005 — Secrets: OS keychain is the product path

**Decision.** YAML 0600 is acceptable for a personal laptop and is well-built (`config.py`). It is not the product secret story. Phase 3 moves tokens/cookies/keys to OS keychain (or equivalent). YAML remains migrate-from and non-secret config (backend overrides, proxy URL with password still sensitive → keychain too).

**Why.** No encryption at rest, Windows ACLs weaker, agent-readable files, `--sync-legacy-twitter` extra plaintext.

**Consequences.** Dependency decision: wrap OS CLIs vs `keyring` extra. Ask Pepe. Never log values. `to_dict()` redaction stays.

---

## ADR-006 — Cookie input is stdin/getpass only

**Decision.** Documented happy path must not paste cookies into agent chat. CLI already has `--stdin` and hidden prompts. Docs and skill must match.

**Why.** Highest-likelihood high-impact finding (`cookie-agent-logs`).

**Consequences.** Rewrite `docs/cookie-export.md` and `SKILL.md:142`. Positional argv secrets stay discouraged (history/process list).

---

## ADR-007 — Official APIs / public CLIs for the commercial set

**Decision.** Supported commercial channels: GitHub (`gh`), Exa (MCP), YouTube (`yt-dlp`), Web (Jina), RSS (`feedparser`). No session-cookie requirement.

**Why.** Sellable, ToS-cleaner, matches "not a wrapper".

**Note.** `yt-dlp` is a public CLI, not YouTube's official API. Pepe already included it in the commercial core. We do not pretend it is YouTube Data API. Document ToS/ToU as the user's problem, same as today.

---

## ADR-008 — SSRF: DNS-pin or stop fetching inside this repo

**Decision.** Phase 2 either (1) resolve DNS and pin to global unicast before Jina/yt-dlp/V2EX/Xueqiu, or (2) delete in-process fetch and let the skill call curl/yt-dlp, with pin on anything we still wrap.

**Why.** Current check is literal IPs + denylist, then skip DNS (`utils/url.py`, `transcribe.py`). Hostname rebinding is the hole.

**Consequences.** Pepe picks mechanism. Do not ship a half-pin that still hands a hostname to yt-dlp.

---

## ADR-009 — `install --system` is never the default documented path

**Decision.** Check-only default stays (`cli.py:261`). Copy-paste install docs are check-only. `--system` is documented with blast radius: other agents' skill dirs + OS packages + mcporter.

**Why.** Any agent with exec can persist our skill into Claude/OpenClaw/OpenCode/Agents and apt-get.

**Consequences.** Phase 2 may add a confirmation flag. That is a public API change: ask first. `--safe` remains an alias of the default.

---

## ADR-010 — Pin dependencies on the default install path

**Decision.** Keep range specs in `pyproject.toml` for flexibility. Make `constraints.txt` the documented/CI/user default (`pip install -c constraints.txt`).

**Why.** yt-dlp talks to the internet. CI is locked; zip-from-main users are not.

**Consequences.** Install docs change in Phase 1. Updating constraints is a deliberate PR (`docs/dependency-locking.md`).

---

## ADR-011 — Doctor honesty without cookie-refresh probes

**Decision.** Never weaken `tests/test_doctor_credential_boundaries.py`. Fix the product signal by distinguishing `live-ok` vs `configured-unverified` vs `missing`. Prefer a new JSON field if Pepe approves; otherwise prose + skill.

**Why.** 8 channels never return `ok`. Agents under-use working backends or ignore doctor. The refusal to run `twitter status` / `gh auth status` is correct.

---

## ADR-012 — MCP stays status/doctor

**Decision.** `get_status` only. Config `read_only=True`. Do not wrap cookie platforms as MCP tools.

**Why.** Audit. Extra MCP tools that hold cookies become the hosted-proxy shape even on stdio.

**Revisit if.** Pepe names a product reason (e.g. expose doctor JSON to a GUI). Still no session-holding tools.

---

## ADR-013 — Leverage the MIT installer; do not rewrite from zero

**Decision.** Fork/leverage. Keep doctor, config, Cookie-Editor policy, private writes, probe argv lists.

**Why.** Routing tables are commodity. Policy work is the expensive part and is already here. License allows it (MIT, "Agent Eyes" 2025).

**Consequences.** Smallest viable change. New files under `product/` and later additive modules. No framework swap. Never modify upstream OSS.

---

## ADR-014 — Version in three places, and the test must assert it

**Decision.** `pyproject.toml`, `agent_reach/__init__.py`, and a test that reads both. CLAUDE.md already requires `tests/test_cli.py`; today that file uses `1.5.0` only as update-comparison fixture data.

**Why.** Contract drift finding. Runtime versions already match.

---

## ADR-015 — Channel contract in docs matches code

**Decision.** Documented contract is `can_handle(url)` + `check(config)`. `read`/`search` are not required. Backends are an ordered candidate list; `check()` sets `active_backend`.

**Why.** `base.py` vs CLAUDE.md. CONTRIBUTING.md still tells people to implement a "unified channel interface" and update `doctor.py` (wrong).

---

## ADR-016 — Do not change public CLI / auth / deps / skill policy without asking

**Decision.** Phase 0 is plan only. Later phases list explicit approval items in `ROADMAP.md`.

**Examples that need a yes:** new `doctor --json` field, `--i-understand-system`, `agent-reach gh`, `keyring` dependency, deleting `WebChannel.read`, skill forbidding gh writes (behavior change for existing users).

---

## ADR-017 — Phase 1 execute encodings (2026-08-13)

**Decision.** Phase 1 may start without re-asking the four ROADMAP approval items. Encoded answers:

1. **README pointer to `product/`:** YES. Docs, not API (F1.2).
2. **Drop skill check-update nudge:** YES. Skill copy in `SKILL.md` + `SKILL_en.md`. Keep the `check-update` CLI. Do not add `config.check_update_on_skill` (F12.1, F12.4).
3. **pyproject description wording:** YES if it is the `description` string plus matching "entire internet" help/docstrings (`__init__.py`, `core.py`, argparse description). NO version bump, NO keywords/classifiers/deps, NO publish. That is not a release (F1.7, F1.8).
4. **`doctor --json` `confidence` field:** NO. Public API. Skip F3.2. Phase 1 doctor honesty is prose only (`format_report` + skill). Do not change JSON keys. Do not remap `warn` → `ok`.

**Why.** Pepe asked for a new-chat prompt that can start. Re-asking inside that chat would stall the work he already scoped.

**Consequences.** A later chat may still approve F3.2. Until then, `ENGINEERING.md` proposed mapping stays a proposal. `CHANNELS.md` must not say Phase 1 ships `confidence=configured`.

**Contradiction fixed.** ROADMAP Phase 1 previously listed those four as unanswered. ENGINEERING.md previously said ask before the README pointer. Both now defer to this ADR for Phase 1 execute.
