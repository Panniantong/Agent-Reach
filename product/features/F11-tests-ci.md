# F11 Tests / CI

**Parent:** none · **Phase:** 1–5 (tests land with the feature they lock) · **Status:** F11.1–F11.3 done

Do not delete or weaken existing tests. Especially: `tests/test_doctor_credential_boundaries.py`, `tests/test_url_security.py`, `tests/test_private_file_writes.py`, `tests/test_cookie_security.py`, `tests/test_mcp_server.py`, `tests/test_probe.py` (no `shell=True`).

33 test modules + `conftest.py` today. Prefer adding `tests/test_docs_contract.py` for greps rather than stuffing `test_cli.py`.

Run `pytest tests/ -v` before any commit Pepe asks for. CI: `.github/workflows/pytest.yml`.

---

## F11.1 Docs / contract grep tests

- **Parent:** F11
- **Phase:** 1
- **Status:** planned
- **Goal:** Contract drift cannot regress silently.
- **Files:** new `tests/test_docs_contract.py` (preferred) or extensions of `tests/test_channel_contracts.py` / `tests/test_cli.py`.
- **Acceptance:** Tests that read files as text (repo root relative to test file):
  - `CLAUDE.md` does not say `13 internet platforms` / require `read(url)` + `search(query)` as the channel contract.
  - `pyproject.toml` description does not contain `entire internet` or `10+`.
  - `docs/install.md` does not cite `~/.agent-reach/config.json`.
  - `CONTRIBUTING.md` does not tell people to update `doctor.py` to register a channel.
  - `agent_reach/skill/SKILL.md` and `SKILL_en.md` do not contain `用户只需提供 cookies` / `The user only provides cookies`.
  - `agent_reach/integrations/mcp_server.py` does not advertise `agent-reach[mcp]` unless that extra exists.
  - `README.md` contains `product/README.md`.
- **Tests:** this feature **is** the tests.
- **Dependencies:** F1.*, F9.2, F12.1 (nudge drop is F11-adjacent greps in F12)
- **Risks:** brittle greps. Use exact phrases from this spec, not `cookies` alone.
- **Approval needed?** no

---

## F11.2 Doctor tests (prose, not new JSON field)

- **Parent:** F11
- **Phase:** 1
- **Status:** planned
- **Goal:** Legend/message changes do not break JSON keys.
- **Files:** `tests/test_doctor.py`, maybe `tests/test_cli.py` doctor mock.
- **Acceptance:**
  - `test_check_all_collects_channel_results` still exact-keys on the six fields (F3.3).
  - `format_report` tests updated for the new legend (F3.1).
  - `tests/test_doctor_credential_boundaries.py` untouched in spirit; extend only if adding a new forbidden probe.
- **Tests:** as above.
- **Dependencies:** F3.1, F3.3, F3.4
- **Risks:** exact string matches on Chinese legend. Prefer substring asserts on the new distinguishing phrases.
- **Approval needed?** no

---

## F11.3 Install / constraints tests

- **Parent:** F11
- **Phase:** 1
- **Status:** planned
- **Goal:** Docs recipes stay pinned and check-only-first.
- **Files:** `tests/test_docs_contract.py` (or `tests/test_integration_script.py` which already greps `test.sh` for `doctor --json`).
- **Acceptance:**
  - `docs/install.md` primary pip recipe includes `-c constraints.txt`.
  - First copy-paste install command is not `--system`.
  - Four skill roots mentioned.
  - `docs/update.md` pip upgrade includes `-c` or an explicit pipx exception.
  - Existing install CLI tests (`tests/test_p0_cli.py`) still prove check-only default.
- **Tests:** this feature is the tests plus existing CLI tests.
- **Dependencies:** F2.1–F2.6, F2.8
- **Risks:** none
- **Approval needed?** no

---

## F11.4 DNS-pin / cookie-paste / XHS flag tests

- **Parent:** F11
- **Phase:** 2
- **Status:** planned
- **Goal:** High findings stay closed.
- **Files:** new `tests/test_dns_pin.py`; greps in `test_docs_contract.py`; XHS header-string tests in `tests/test_cookie_security.py` or `tests/test_private_file_writes.py`.
- **Acceptance:** See F5.1, F4.1, F4.3, F2.7. `test_url_security.py` and cookie-boundary tests still pass.
- **Tests:** this feature.
- **Dependencies:** F2.7, F4.1, F4.3, F5.*
- **Risks:** fake `getaddrinfo` must cover IPv4 and IPv6.
- **Approval needed?** no

---

## F11.5 Keychain + twitter path tests

- **Parent:** F11
- **Phase:** 3
- **Status:** planned
- **Goal:** Secret storage and ADR-004 do not land untested.
- **Files:** new `tests/test_secrets.py`; `tests/test_twitter_channel.py` (already covers `twitter_cli_child_env`).
- **Acceptance:** See F6.* and F4.4. Fake keychain backend. Redaction still holds (`tests/test_config.py`).
- **Tests:** this feature.
- **Dependencies:** F6, F4.4
- **Risks:** CI without macOS Keychain. Fake backend is mandatory.
- **Approval needed?** no

---

## F11.6 gh allowlist tests

- **Parent:** F11
- **Phase:** 4
- **Status:** planned
- **Goal:** Wrapper (if shipped) fail-closes on writes.
- **Files:** new `tests/test_gh_readonly.py`. Skill greps for write commands.
- **Acceptance:** See F7.2. If Pepe picks skill-only, tests are greps only (F7.1) and this module is skipped.
- **Tests:** this feature.
- **Dependencies:** F7
- **Risks:** testing argv parsing vs actually exec'ing `gh`. Mock exec.
- **Approval needed?** no
