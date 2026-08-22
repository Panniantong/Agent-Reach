# F6 Secrets

**Parent:** none · **Phase:** 3 · **Status:** planned · **Audit:** plaintext-secrets, twitter-dead-config (via F4.4)

ADR-005: OS keychain is the product path. YAML 0600 is well-built (`config.py:46-103`) and stays as migrate-from / non-secret config. Do not add a runtime dep unless Pepe picks `keyring`.

Phase 1–2 must not change auth storage.

---

## F6.1 Keychain as product path, YAML fallback

- **Parent:** F6
- **Phase:** 3
- **Status:** planned
- **Goal:** Tokens, cookies, and API keys are not the README security headline as plaintext YAML.
- **Files:** new `agent_reach/secrets.py` (DIRECTORY.md). `agent_reach/config.py` `get` / `set` (`:159-168` env uppercase fallback). `cli.py` configure. Sensitive name markers already in `to_dict()` (`config.py:211-233`): key, token, password, proxy, cookie, secret, session, sessdata, csrf, auth, cred, ct0.
- **Acceptance:**
  - Documented product path for `github_token`, `groq` / `openai` keys, and any Exa key if we ever store one: keychain.
  - Cookies in YAML are power-user leftover.
  - `to_dict()` redaction stays.
  - Never log values.
- **Tests:** F11.5 round-trip on a fake backend (no real Keychain in CI).
- **Dependencies:** F6.2 pick
- **Risks:** first real auth-storage change. Windows ACL story weaker; document.
- **Approval needed?** no for the direction (frozen). yes for mechanism (F6.2).

---

## F6.2 `keyring` extra vs OS CLI wrappers

- **Parent:** F6
- **Phase:** 3
- **Status:** **blocked-on-Pepe**
- **Goal:** Pick how we talk to the OS store.
- **Files:** `pyproject.toml` optional-dependencies (only if `keyring`). Else wrap `security` (macOS), `secret-tool` (libsecret), Windows credential CLI. `ENGINEERING.md` proposed service name `agent-reach`, account = config key.
- **Acceptance:** Exactly one approach in code. Tests fake the backend. No required runtime dep unless Pepe approved `keyring`.
- **Tests:** in-memory backend in CI.
- **Dependencies:** Pepe pick
- **Risks:** `keyring` is a dep. OS CLIs differ by platform and may be missing in CI (hence fake backend).
- **Approval needed?** **yes.** Dependency decision.

---

## F6.3 YAML → keychain migration

- **Parent:** F6
- **Phase:** 3
- **Status:** **blocked-on-Pepe**
- **Goal:** Existing `~/.agent-reach/config.yaml` users do not lose secrets and do not leak them in logs.
- **Files:** `config.py`, `secrets.py`, configure, doctor world-readable warning (`doctor.py:114-127`).
- **Acceptance:** Algorithm in ENGINEERING.md, confirm at implement:
  1. Read: keychain → YAML → env.
  2. Write: keychain; YAML only if `AGENT_REACH_SECRETS=yaml` **or** dual-write until migration complete (Pepe picks).
  3. Migration must not print secret values.
- **Tests:** migrate a temp YAML with a fake token into the fake keychain; YAML leftover handling as picked.
- **Dependencies:** F6.2
- **Risks:** dual-write leaves plaintext on disk (defeats the point if it never stops). Dual-write as a one-release bridge is OK if documented.
- **Approval needed?** **yes.** Dual-write vs keychain-only vs env override.

---

## F6.4 File perms 0600 stay as fallback

- **Parent:** F6
- **Phase:** 3
- **Status:** planned (keep)
- **Goal:** YAML leftover is still symlink-safe and mode 0600.
- **Files:** `config.py:46-103`, `utils/paths.py`, `tests/test_private_file_writes.py`.
- **Acceptance:** Do not weaken atomic write, `fchmod 0600`, symlink component refusal. Doctor still warns if group/other readable. Keychain does not replace those controls for whatever remains in YAML (backend overrides, non-secret keys).
- **Tests:** existing private-write tests stay green. Do not skip them on "we have keychain now".
- **Dependencies:** none
- **Risks:** someone deletes 0600 because "secrets moved". Do not.
- **Approval needed?** no

---

## F6.5 `--sync-legacy-twitter` stays off by default

- **Parent:** F6
- **Phase:** 3
- **Status:** planned (lock)
- **Goal:** Do not add more plaintext stores.
- **Files:** `cli.py:125-128`, `cookie_extract.py` writes `~/.config/xfetch/session.json` and `~/.config/bird/credentials.env` only if that flag is set.
- **Acceptance:** Flag remains opt-in. Docs say it writes extra plaintext. Default configure twitter-cookies does not sync legacy.
- **Tests:** existing tests that the flag is required for those writes.
- **Dependencies:** F4.4 (if B, maybe deprecate the flag; still ask)
- **Risks:** none
- **Approval needed?** no to keep default off. yes to remove the flag.

---

## F6.6 Uninstall deletes keychain items we created

- **Parent:** F6
- **Phase:** 3
- **Status:** planned
- **Goal:** `uninstall` does not leave keychain orphans.
- **Files:** `cli.py` `_cmd_uninstall`, `secrets.py`. Today uninstall removes `~/.agent-reach/` and skill copies (`cli.py:136-140` `--keep-config`).
- **Acceptance:** Uninstall deletes `agent-reach` service items we wrote. `--keep-config` keeps YAML **and** keychain (same meaning: keep secrets). Document it.
- **Tests:** fake backend: uninstall removes items; `--keep-config` does not.
- **Dependencies:** F6.1
- **Risks:** deleting unrelated keychain items if service name is too broad. Use a dedicated service name.
- **Approval needed?** no (once F6.2 exists)
