# Execution checklist

Tick in order. Do not start Phase N+1 until Phase N exit criteria pass. Details: `FEATURES.md` and `product/features/`.

Public API / auth / deps / skill-policy: only when the feature file says approval is yes **and** Pepe has answered, except the Phase 1 encodings in ADR-017.

---

## Phase 0 — Plan (this directory)

- [x] `product/` strategy docs (PRD, ARCHITECTURE, SECURITY, ROADMAP, SCOPE, DECISIONS, CHANNELS, ENGINEERING, DIRECTORY)
- [x] Product plan canvas
- [x] Security audit canvas left intact
- [x] Feature inventory (`FEATURES.md` + `features/F01`–`F12`)
- [x] This checklist
- [x] `NEW-CHAT-PROMPT.md`
- [x] Zero production code. No commit unless Pepe asks

**Exit:** Pepe can paste `NEW-CHAT-PROMPT.md` into a new chat and execute Phase 1 without guessing.

---

## Phase 1 — Contract truth + pins + doctor prose + nudge drop

Branch from latest main. Do not bump version (`1.5.0`). Do not add runtime deps. Do not change auth storage. Do not add `doctor --json` keys.

### F1 Contract truth

- [x] F1.1 `CLAUDE.md`: 15 channels; `can_handle` + `check`; `core.py` is doctor-only; class name `Channel`
- [x] F1.2 `README.md`: pointer to `product/README.md`; GitHub row not Issue/PR/Fork unlock
- [x] F1.3 `SKILL.md` + `SKILL_en.md`: kill cookie-paste one-liners
- [x] F1.4 `CONTRIBUTING.md`: registry auto-discovers; do not update `doctor.py` to add a channel
- [x] F1.5 Version assert: `pyproject.toml` == `__version__` (still `1.5.0`)
- [x] F1.6 `docs/install.md`: `config.yaml` not `config.json`
- [x] F1.7 `pyproject.toml` `description` only (no version bump, no keywords/deps)
- [x] F1.8 `__init__.py` / `core.py` / `cli.py` argparse: no "entire internet"
- [x] F1.9 `docs/README_en.md` (JA/KO if needed): no entire-internet tagline
- [x] F1.10 `len(get_all_channels()) == 15`
- [x] F1.11 Skill zero-config numeric claim honest or removed

### F2 Install hygiene (docs)

- [x] F2.1 `docs/install.md` + `docs/dependency-locking.md`: `-c constraints.txt` on default pip path
- [x] F2.2 `--system` blast-radius section (four skill roots + OS packages + mcporter)
- [x] F2.3 Check-only default unchanged (`cli.py:261`)
- [x] F2.4 Copy-paste one-liner is check-only
- [x] F2.5 Skill install paths (four roots + locale pick)
- [x] F2.6 `docs/update.md` constraints recipe
- [x] F2.8 pipx cannot take `-c`; documented
- [x] F2.9 Uninstall docs match the four roots

### F3 Doctor honesty (no JSON field)

- [x] F3.1 `format_report` legend + skill: `warn` ≠ off
- [x] F3.2 **SKIP** `confidence` field (public API, blocked)
- [x] F3.3 JSON keys remain the six existing ones
- [x] F3.4 Never-ok channel list in skill or install.md

### F8 / F9 / F12 (Phase 1 slice)

- [x] F8.1 README commercial set first (docs only; no `--channels` behavior change)
- [x] F9.2 `mcp_server.py` stop advertising `[mcp]` extra
- [x] F12.1 Drop skill check-update standing rule (both languages)
- [x] F12.2 Keep `check-update` command
- [x] F12.3 Do not teach `watch` as a post-task skill rule
- [x] F12.4 **SKIP** `config.check_update_on_skill`

### F11 Phase 1 tests

- [x] F11.1 `tests/test_docs_contract.py` (or equivalent greps)
- [x] F11.2 Doctor legend tests; credential-boundary tests still pass
- [x] F11.3 Install/constraints/check-only greps
- [x] `pytest tests/ -v` green

**Out of Phase 1:** F2.7, F3.5, F4.1–F4.6 (except F1.3), F5–F7, F8.2–F8.4, F10, F11.4–F11.6.

**Exit:** CLAUDE.md / README / registry all say 15; contract matches `base.py`; version asserted; install docs use constraints; default still check-only; cookie-refresh tests pass; doctor JSON schema unchanged; skill has no cookie-paste one-liner and no post-task check-update. **Met on branch `phase-1-contract-hygiene` (pytest 605 passed; follow-up docs uncommitted until Pepe asks).**

---

## Phase 2 — Security hardening

Pepe must pick F5.1 (DNS-pin vs stop fetch) before fetch code. Do not add `--i-understand-system` unless asked.

- [ ] F4.1 Cookie-export + guides: stdin/getpass only
- [ ] F4.2 Documented configure path is `--stdin` / TTY getpass
- [ ] F4.3 XHS header-string `secure`/`httpOnly` true
- [ ] F4.6 Positional secrets: docs + warning only unless Pepe approves removal
- [ ] F2.7 `--system` prints blast radius (print-only unless flag approved)
- [ ] F5.1 Mechanism picked and applied
- [ ] F5.2 WebChannel.read pinned or gone
- [ ] F5.3 V2EX pinned or skill curl
- [ ] F5.4 Xueqiu pinned or stopped
- [ ] F5.5 transcribe / yt-dlp URL check
- [ ] F5.6 RSS `can_handle` tightened or marked unused
- [ ] F3.5 `watch` does not treat by-design `warn` as broken
- [ ] F11.4 DNS-pin, cookie-paste grep, XHS flags, `--system` print tests
- [ ] `pytest tests/ -v` green

**Exit:** No documented cookie-in-chat happy path. `--system` is loud. In-process fetch DNS-pins or is gone. XHS header-string cookies not marked insecure.

---

## Phase 3 — Secrets + Twitter path

Pepe must pick F6.2 (keyring vs OS CLI), F6.3 (migration), F4.4 (Twitter A vs B).

- [ ] F6.2 Mechanism picked
- [ ] F6.1 Keychain product path
- [ ] F6.3 Migration without logging values
- [ ] F6.4 YAML 0600 + symlink refusal still on
- [ ] F6.5 `--sync-legacy-twitter` still opt-in
- [ ] F6.6 Uninstall deletes keychain items we created
- [ ] F4.4 Twitter inject **or** stop storing
- [ ] F11.5 Fake-backend secret tests
- [ ] `pytest tests/ -v` green

**Exit:** Documented product secrets are keychain. Twitter lie is gone. No new runtime dep unless approved.

---

## Phase 4 — Read-only GitHub + gating

Pepe must pick F7.2 (wrapper vs skill-only) and F8.2 (`--channels=all`).

- [ ] F7.1 `dev.md` read-only
- [ ] F7.2 Wrapper **or** documented skill-only exception
- [ ] F7.3 OpenCLI skill examples stay read-only
- [ ] F8.1 Skill power-user heading
- [ ] F8.2 `--channels` default vs `all` warning
- [ ] F8.3 No channel deletions; bird/xhs-cli un-marketed
- [ ] F8.4 LinkedIn Jina default vs MCP gated
- [ ] F4.5 `--from-browser` twitter/xhs still blocked
- [ ] F11.6 gh allowlist tests (if wrapper)
- [ ] `pytest tests/ -v` green

**Exit:** Commercial set is the default story. GitHub writes not in default skill. Cookie channels labeled power-user / burner. Enforcement exists unless Pepe accepted skill-only.

---

## Phase 5 — Ship

Pepe must pick F10.1 (1.6 vs 2.0), F10.2 (PyPI), F10.5 (tag). Never push main.

- [ ] F10.6 CHANGELOG catch-up
- [ ] F10.4 Three-place bump
- [ ] F10.3 CI still constraints + wheel-gate
- [ ] F9.2 optional `[mcp]` extra only if approved
- [ ] Root `SECURITY.md`: we do not host cookies
- [ ] Tag on merged PR

**Exit:** Tagged release whose install docs match CI. Version loci match. Constraints on the documented install. No cookie hosting in the security policy.
