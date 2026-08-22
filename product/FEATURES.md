# Feature inventory

Master index of every shippable unit. Details live in `product/features/`. Execute in phase order via `CHECKLIST.md`. Do not start from memory.

Status: **planned** (not started in code) · **blocked-on-Pepe** (needs a pick before code) · **done** (shipped in repo). Phase 1 subfeatures below are **done** on `phase-1-contract-hygiene`.

Counts from code, 2026-08-13, v1.5.0: **15** channels in `agent_reach/channels/__init__.py:26-42`. Contract is `can_handle` + `check` (`base.py:41-70`). `AgentReach` is doctor-only (`core.py:23-42`).

## How to use

1. Read `SCOPE.md` + `DECISIONS.md` (frozen).
2. Open the feature file for the phase you are in.
3. Tick `CHECKLIST.md`. Stop at phase boundary.
4. Public API / auth / deps / skill-policy: only if the subfeature says Approval = yes and Pepe already answered, or the Phase 1 execute encodings in ADR-017.

## Index

| ID | Name | Phase | Status | Approval | Spec |
|----|------|-------|--------|----------|------|
| F1 | Contract truth | 1 | done | mixed | [F01](features/F01-contract-truth.md) |
| F2 | Install/update hygiene | 1–2 | phase-1 done | mixed | [F02](features/F02-install-hygiene.md) |
| F3 | Doctor honesty | 1 | phase-1 done | JSON field blocked | [F03](features/F03-doctor-honesty.md) |
| F4 | Cookie/auth UX | 1–4 | planned | mixed | [F04](features/F04-cookie-auth-ux.md) |
| F5 | SSRF / fetch | 2 | planned | pin vs stop | [F05](features/F05-ssrf-fetch.md) |
| F6 | Secrets | 3 | planned | keyring vs OS CLI | [F06](features/F06-secrets.md) |
| F7 | Read-only policy | 4 | planned | gh wrapper | [F07](features/F07-read-only-policy.md) |
| F8 | Channel productization | 1+4 | phase-1 docs done | `--channels=all` | [F08](features/F08-channel-productization.md) |
| F9 | MCP | 1+keep | F9.2 done | no new tools | [F09](features/F09-mcp.md) |
| F10 | Packaging/distribution | 5 | planned | 1.6 vs 2.0 | [F10](features/F10-packaging.md) |
| F11 | Tests/CI | 1–5 | F11.1–F11.3 done | no | [F11](features/F11-tests-ci.md) |
| F12 | Telemetry/update | 1 | done | nudge YES | [F12](features/F12-telemetry-update.md) |

## Subfeatures (all)

| ID | Name | Parent | Phase | Status | Approval needed? |
|----|------|--------|-------|--------|------------------|
| F1.1 | CLAUDE.md contract + count | F1 | 1 | done | no |
| F1.2 | README commercial story + `product/` pointer | F1 | 1 | done | no (pointer YES) |
| F1.3 | Skill dual-language cookie-paste line | F1 | 1 | done | no |
| F1.4 | CONTRIBUTING registry truth | F1 | 1 | done | no |
| F1.5 | Version three-place assert | F1 | 1 | done | no |
| F1.6 | `config.json` → `config.yaml` in install docs | F1 | 1 | done | no |
| F1.7 | pyproject `description` wording | F1 | 1 | done | no (text only, no release) |
| F1.8 | Kill "entire internet" in package strings | F1 | 1 | done | no (docstrings/help, not flags) |
| F1.9 | Translation README taglines | F1 | 1 | done | no |
| F1.10 | Registry count test `== 15` | F1 | 1 | done | no |
| F1.11 | Skill "zero-config" count honesty | F1 | 1 | done | no |
| F2.1 | `constraints.txt` on default install path | F2 | 1 | done | no |
| F2.2 | `--system` blast-radius docs | F2 | 1 | done | no |
| F2.3 | Check-only default stays | F2 | 1 | done (lock) | no |
| F2.4 | Documented one-liner is check-only | F2 | 1 | done | no |
| F2.5 | Skill install paths documented | F2 | 1 | done | no |
| F2.6 | `docs/update.md` constraints recipe | F2 | 1 | done | no |
| F2.7 | `--system` CLI blast print | F2 | 2 | planned | yes if new flag |
| F2.8 | pipx/`-c` limitation documented | F2 | 1 | done | no |
| F2.9 | Uninstall skill-dir list stays accurate | F2 | 1 | done (docs) | no |
| F3.1 | Login-channel false-negatives, prose | F3 | 1 | done | no |
| F3.2 | `doctor --json` `confidence` field | F3 | 1 | **blocked-on-Pepe** | yes (public API). Skip Phase 1 |
| F3.3 | JSON schema freeze (`status` enum) | F3 | 1 | done (lock) | no |
| F3.4 | Document which channels can never be `ok` | F3 | 1 | done | no |
| F3.5 | `watch` treats all `warn` as issues | F3 | 2 | planned | no |
| F4.1 | Kill paste-to-agent in cookie-export + guides | F4 | 2 | planned | no |
| F4.2 | Stdin/getpass is the only documented path | F4 | 2 | planned | no |
| F4.3 | XHS header-string `httpOnly`/`secure` | F4 | 2 | planned | no |
| F4.4 | Twitter unused YAML tokens | F4 | 3 | **blocked-on-Pepe** | yes (A vs B) |
| F4.5 | `--from-browser` twitter/xhs stay blocked | F4 | 4 | planned (lock+gate) | yes if extra flag |
| F4.6 | Positional secret argv discourage | F4 | 2 | planned | yes if removing positional |
| F5.1 | DNS-pin helper vs stop in-process fetch | F5 | 2 | **blocked-on-Pepe** | yes (mechanism) |
| F5.2 | `WebChannel.read` | F5 | 2 | planned | yes if deleting method |
| F5.3 | V2EX owned fetch | F5 | 2 | planned | no (follows F5.1) |
| F5.4 | Xueqiu owned fetch + CookieJar | F5 | 2 | planned | no (follows F5.1) |
| F5.5 | yt-dlp / transcribe URL checks | F5 | 2 | planned | no (follows F5.1) |
| F5.6 | RSS substring `can_handle` | F5 | 2 | planned | no |
| F6.1 | Keychain as product path, YAML fallback | F6 | 3 | planned | no (direction frozen) |
| F6.2 | `keyring` extra vs OS CLI wrappers | F6 | 3 | **blocked-on-Pepe** | yes (dep) |
| F6.3 | YAML → keychain migration | F6 | 3 | **blocked-on-Pepe** | yes (behavior) |
| F6.4 | File perms 0600 stay as fallback | F6 | 3 | planned (keep) | no |
| F6.5 | `--sync-legacy-twitter` stays off by default | F6 | 3 | planned (lock) | no |
| F6.6 | Uninstall deletes keychain items we created | F6 | 3 | planned | no |
| F7.1 | Skill GitHub read-only wording | F7 | 4 | planned | no (policy; listed in ROADMAP) |
| F7.2 | `agent-reach gh` allowlist wrapper | F7 | 4 | **blocked-on-Pepe** | yes (public CLI) |
| F7.3 | OpenCLI blast radius (no write teaching) | F7 | 4 | planned | no |
| F8.1 | Commercial set first in README/skill | F8 | 1 docs / 4 gate | phase-1 docs done | no for docs |
| F8.2 | `--channels=all` vs explicit names | F8 | 4 | **blocked-on-Pepe** | yes |
| F8.3 | Per-channel keep / API / power-user | F8 | 4 | planned | no (no deletions) |
| F8.4 | LinkedIn split (Jina vs MCP login) | F8 | 4 | planned | no |
| F9.1 | MCP stays `get_status` only | F9 | keep | planned (lock) | yes to grow tools |
| F9.2 | Advertised `[mcp]` extra does not exist | F9 | 1 docs / 5 extra | phase-1 docs done | yes to add extra |
| F10.1 | Version 1.6 vs 2.0 | F10 | 5 | **blocked-on-Pepe** | yes |
| F10.2 | PyPI name / publish | F10 | 5 | **blocked-on-Pepe** | yes |
| F10.3 | CI wheel-gate + constraints stay | F10 | 5 | planned (keep+extend) | no |
| F10.4 | Three version loci on bump | F10 | 5 | planned | no |
| F10.5 | Tag via PR, never push main | F10 | 5 | planned | yes (tag) |
| F10.6 | CHANGELOG catch-up 1.3.1 → product cut | F10 | 5 | planned | no |
| F11.1 | Docs/contract grep tests | F11 | 1 | done | no |
| F11.2 | Doctor tests (prose, not new JSON field) | F11 | 1 | done | no |
| F11.3 | Install/constraints tests | F11 | 1 | done | no |
| F11.4 | DNS-pin / cookie-paste / xhs flag tests | F11 | 2 | planned | no |
| F11.5 | Keychain + twitter path tests | F11 | 3 | planned | no |
| F11.6 | gh allowlist tests | F11 | 4 | planned | no |
| F12.1 | Drop skill check-update nudge | F12 | 1 | done | no (YES encoded) |
| F12.2 | Keep `check-update` as user-invoked | F12 | 1 | done (keep) | no |
| F12.3 | `watch` GitHub GET stays user-scheduled | F12 | 1 | done (keep) | no |
| F12.4 | `config.check_update_on_skill` | F12 | skip | **blocked-on-Pepe** | yes (config key). Do not add |

## Phase 1 execute set (done on `phase-1-contract-hygiene`)

Did these. Do not do later phases in the Phase 1 chat.

In: F1.1–F1.11, F2.1–F2.6, F2.8–F2.9, F3.1, F3.3–F3.4, F8.1 (docs only), F9.2 (docs only), F11.1–F11.3, F12.1–F12.3.

Out: F3.2, F3.5, F2.7, F4.1–F4.6 except F1.3 already covers the skill cookie line, F5–F7, F8.2–F8.4, F10, F11.4–F11.6, F12.4.

## Dependencies (high level)

```
F1 + F11.1 + F12.1  (Phase 1, parallel)
F2.1–F2.6 + F3.1/F3.4  (Phase 1, parallel)
  → F4.1 + F2.7 + F5.*  (Phase 2, after F5.1 pick)
    → F6.* after F6.2/F6.3 picks
      → F7 + F8.2 after wrapper / --channels picks
        → F10 after version/PyPI picks
```

F9.1 is a lock across all phases. F3.2 is not on the critical path; prose (F3.1) unblocks Phase 1.

## Do not invent

No hosted cookie proxy. No wrapper API (`AgentReach.read` stays unexported). No QR. No `--system` as the one-liner. No weakening `tests/test_doctor_credential_boundaries.py`.
