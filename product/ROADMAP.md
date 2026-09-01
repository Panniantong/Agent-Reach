# Roadmap

Execute in order. Do not start Phase N+1 until Phase N exit criteria pass. Phase 0 is this directory.

Shippable units: `FEATURES.md` (index) + `features/F01`–`F12` (full AC). Tick `CHECKLIST.md`. Paste `NEW-CHAT-PROMPT.md` to start Phase 1.

Every phase lists: goal, feature IDs, files, tests, risks, exit criteria, **what Pepe must approve** before code lands.

Public API, auth, dependency, and skill-policy changes always need a yes from Pepe. This file says so per phase instead of burying it.

---

## Phase 0 — Plan directory + canvas + feature inventory (this pass)

**Goal.** Pepe can execute without guessing.

**Files.** `product/*` including `FEATURES.md`, `features/F01`–`F12`, `CHECKLIST.md`, `NEW-CHAT-PROMPT.md`. Canvas at `canvases/agent-reach-product-plan.canvas.tsx`. No `agent_reach/` Python, CLI, tests, pyproject, or skill runtime edits.

**Tests.** None. No production behavior change.

**Risks.** Plan drift if someone starts coding from memory instead of these files.

**Exit criteria.**

- [x] `product/` filled (not stubs).
- [x] Canvas: phases, product vs out-of-scope, security map, directory tree, glue vs ships.
- [x] Feature inventory: every F* / F*.* has ID, files, AC, tests, deps, risks, approval.
- [x] Audit verdict encoded: leverage MIT, no cookie SaaS, commercial core = GitHub + Exa + YouTube + RSS/Jina.
- [x] No commit.

**Pepe must approve.** Nothing for Phase 0. Read `SCOPE.md` + `DECISIONS.md`. Phase 1 starts when he pastes `NEW-CHAT-PROMPT.md`.

---

## Phase 1 — Docs/contract truth + install defaults + pins + doctor honesty

**Goal.** Stop lying. Make doctor a signal in **prose**. Pin deps on the path users actually run. Low risk.

**Feature IDs.** F1.1–F1.11, F2.1–F2.6, F2.8–F2.9, F3.1, F3.3–F3.4, F8.1 (docs), F9.2 (docs), F11.1–F11.3, F12.1–F12.3. Checklist: `CHECKLIST.md`. Specs: `features/F01`–`F03`, `F08`, `F09`, `F11`, `F12`.

**Files (expected).**

- `CLAUDE.md` — 15 channels; contract is `can_handle` + `check`; version three-place rule with a real test (F1.1, F1.5).
- `README.md` — kill "entire internet" as a product claim; commercial set first; pointer to `product/`; GitHub row must not advertise Issue/PR/Fork as the unlock (F1.2, F8.1).
- `pyproject.toml` `description` only — curated backends, not "entire internet" / "10+". No version bump. No other metadata (F1.7).
- `agent_reach/__init__.py`, `core.py`, `cli.py` argparse description — same claim, no flag changes (F1.8).
- `docs/install.md` — check-only copy-paste only; `pip install -c constraints.txt`; fix `config.json` → `config.yaml`; `--system` blast radius; skill paths (F1.6, F2.*).
- `docs/update.md` — same constraints recipe (F2.6).
- `docs/dependency-locking.md` — default path, not just dev (F2.1).
- `docs/README_en.md` (JA/KO if needed) — tagline (F1.9).
- `CONTRIBUTING.md` — drop "update doctor.py to include the new channel" (F1.4).
- `agent_reach/skill/SKILL.md` (+ `SKILL_en.md`) — remove cookie-paste one-liners (F1.3); remove unsolicited `check-update` (F12.1); keep cookie-refresh explanation; never-ok note (F3.4).
- `agent_reach/doctor.py` `format_report` — legend honesty, no new JSON keys (F3.1, F3.3).
- `agent_reach/integrations/mcp_server.py` — stop advertising `[mcp]` extra (F9.2).
- `tests/test_cli.py` or `tests/test_docs_contract.py` — `__version__` matches pyproject (F1.5).
- `tests/test_channel_contracts.py` — `len(get_all_channels()) == 15` (F1.10).

**Tests.** F11.1–F11.3. Version equality. Channel count == 15. Existing suite still green (`pytest tests/ -v`). Grep tests for CLAUDE.md / cookie one-liners / constraints / `config.json`.

**Risks.** Doc-only PRs are easy to under-review. Skill text changes agent behavior (fewer update GETs, less cookie-paste prompting). Do **not** change doctor JSON schema this phase.

**Exit criteria.**

- [x] CLAUDE.md, README commercial story, and registry all say 15.
- [x] Channel contract docs match `base.py`.
- [x] `__version__` asserted (still `1.5.0`).
- [x] Documented install uses `constraints.txt`.
- [x] Default install still check-only.
- [x] Cookie-refresh refusal tests still pass.
- [x] Doctor honesty: skill/report text is unambiguous. Agents are told not to treat `warn` as off. **No** new `confidence` field.

**Pepe must approve.** Encoded in ADR-017 for this execute. Do not re-ask unless you would violate them:

1. pyproject description wording: YES, description string + matching help/docstrings only. No release, no version bump.
2. `doctor --json` new field: NO. Skip F3.2.
3. Skill: drop check-update nudge: YES (F12.1).
4. README pointer to `product/`: YES (F1.2). Chinese README: commercial-table + GitHub row + pointer, not a full rewrite.

---

## Phase 2 — Security hardening

**Goal.** Close high-likelihood and high-impact glue holes that are not secret-storage.

**Files (expected).** Feature IDs F4.1–F4.3, F4.6, F2.7, F5.1–F5.6, F3.5, F11.4. Specs: `features/F02`, `F03`, `F04`, `F05`.

- `docs/cookie-export.md` — stdin/getpass only. Delete "Paste the result to your Agent" and the "Here are my Twitter cookies: [paste]" table.
- `agent_reach/guides/setup-twitter.md`, `setup-xiaohongshu.md` — same.
- `skill/SKILL.md` — no cookie paste.
- `docs/install.md` / README — `--system` blast radius: skill dirs listed, apt/brew/npm, mcporter writes.
- `cli.py` — print blast radius when `--system` is set. **Ask before** adding `--i-understand-system`.
- `utils/url.py` + `transcribe.py` + `web.py` + `v2ex.py` + `xueqiu.py` — DNS-pin helper **or** remove in-process fetch.
- `cli.py` XHS header-string path — do not set `httpOnly:false`, `secure:false`.
- `rss.py` — tighten `can_handle` or mark unused in tests.

**Tests.**

- DNS-pin: hostname resolving to RFC1918 / link-local / metadata IP is rejected; global unicast allowed. Fake resolver.
- Docs grep: no "paste" cookies to agent in skill + cookie-export + guides.
- XHS synthesized cookie flags.
- `test_url_security.py` still passes (host_matches unchanged).
- `test_doctor_credential_boundaries.py` still passes.

**Risks.** DNS-pin can break IPv6 / dual-stack / Happy Eyeballs if done naively. Removing `WebChannel.read` is fine (nothing in `AgentReach` calls it) but tests in `test_web_channel.py` must be updated. `--system` extra flag is a public API change.

**Exit criteria.**

- [ ] No documented happy path pastes cookies into chat.
- [ ] `--system` cannot be missed as a high-blast operation.
- [ ] In-process fetch DNS-pins or is gone.
- [ ] XHS header-string cookies are not marked insecure.
- [ ] High findings cookie-agent-logs, agent-system-writes, dns-rebinding, owned-fetchers addressed.

**Pepe must approve.**

1. DNS-pin vs stop in-process fetch (pick one).
2. Any new CLI flag for `--system`.
3. Whether `WebChannel.read` is deleted (internal, but it is a method on a public-ish class).

---

## Phase 3 — Secret storage + Twitter token path

**Goal.** Product secrets are not plaintext YAML. Twitter config either works or we stop lying.

**Files (expected).** Feature IDs F6.1–F6.6, F4.4, F11.5. Specs: `features/F06`, `F04`.

- New `agent_reach/secrets.py` (or similar) wrapping OS keychain via `security`/`secret-tool` **or** optional `keyring` extra.
- `config.py` — read keychain first for token/cookie/key names; YAML as migrate-from.
- `cli.py` configure — write keychain; refuse to print values.
- Twitter: implement ADR-004 (inject child env via wrapper **or** stop storing).
- Doctor permission check still warns on world-readable YAML leftovers.
- `--sync-legacy-twitter` stays off by default; docs say it writes extra plaintext files.

**Tests.**

- Round-trip set/get/delete on a fake keychain backend in tests (no real Keychain required in CI).
- Redaction still holds.
- Twitter: wrapper sets env for child only, never mutates `os.environ`; **or** configure twitter-cookies does not persist YAML.

**Risks.** First real auth-storage change. Windows ACL story is weaker; document. `keyring` is a runtime dep if chosen. Migrating existing `config.yaml` cookies must not log them.

**Exit criteria.**

- [ ] Documented product path for GitHub token / Groq / OpenAI / Exa (if any) is keychain.
- [ ] Cookie YAML is power-user leftover, not the README security table's headline.
- [ ] Twitter lie is gone (inject or don't store).
- [ ] No new runtime dep unless Pepe approved it.

**Pepe must approve.**

1. keyring extra vs OS CLI wrappers (dependency).
2. Twitter option A (wrapper inject) vs B (stop storing).
3. Migration behavior for existing `config.yaml`.

---

## Phase 4 — Read-only GitHub + commercial set + gated cookies

**Goal.** The default product is official APIs / public CLIs. Cookie/OpenCLI is clearly optional. GitHub writes are not the default and are enforced.

**Files (expected).** Feature IDs F7.1–F7.3, F8.1–F8.4, F4.5, F11.6. Specs: `features/F07`, `F08`.

- `skill/references/dev.md` — read-only command set.
- `SKILL.md` — commercial commands in the quick list; cookie platforms in a "power user" section with burner warning.
- GitHub wrapper or allowlist (mechanism from ADR-003).
- `cli.py` `--channels=` help text: commercial vs power-user.
- README platform table: commercial first; cookie rows labeled power-user / burner.
- `--from-browser` remains blocked for twitter/xhs; xueqiu/bilibili documented as power-user.

**Tests.**

- Wrapper rejects `gh issue create`, `gh pr create`, `gh repo fork`, `gh repo create`.
- Wrapper allows `gh search`, `gh repo view`, `gh issue list`, `gh pr view`.
- Cookie security tests still block twitter/xhs browser extract.
- Skill grep: no `gh issue create` in the default skill references.

**Risks.** Users who already use AR as a GitHub write helper will notice. Wrapper must not claim to be `gh` on PATH. OpenCLI platforms stay in the tree; gating is install + docs + skill, not deletion.

**Exit criteria.**

- [ ] Commercial set is the default story.
- [ ] GitHub writes are not in the default skill.
- [ ] Enforcement exists (not just prose), unless Pepe explicitly accepts skill-only.
- [ ] Cookie channels are labeled power-user / burner-only.

**Pepe must approve.**

1. gh enforcement mechanism (wrapper vs skill-only).
2. Whether power-user channels stay installed by `--channels=all`.
3. Any public CLI change (`agent-reach gh`).

---

## Phase 5 — Packaging, CI, versioning, distribution

**Goal.** Ship as a real product, still local-first.

**Files (expected).** Feature IDs F10.1–F10.6, F9.2 extra if approved. Specs: `features/F10`.

- `CHANGELOG.md` — catch up from 1.3.1; product cut notes.
- Version bump in **three places** (pyproject, `__init__.py`, test assert).
- GitHub Actions: keep constraints + wheel-gate; add ruff/mypy if we want the CONTRIBUTING commands to be real in CI.
- Published install recipe: pipx/pip from a tag, always `-c constraints.txt` or a lock extra.
- `SECURITY.md` (repo root) — add "we do not host cookies" to scope.
- Optional: PyPI name collision note stays (install.md already says do not install the unrelated PyPI `agent-reach`).

**Tests.** Existing CI + version assert + wheel skill files. No live platform tests (those stay upstream).

**Risks.** Version bump without changelog. PyPI name is not this project. Tagging main without a freeze.

**Exit criteria.**

- [ ] Tagged release whose install docs match what CI tests.
- [ ] Three-place version matches.
- [ ] Constraints on the default documented install.
- [ ] Security policy mentions local-first / no cookie hosting.

**Pepe must approve.**

1. Version number for the product cut (1.6.0 vs 2.0.0). 2.0 if we treat commercial-set + keychain as a break in story; 1.6 if CLI flags stay compatible.
2. Whether to publish to PyPI under a non-colliding name.
3. Release / tag. Never push to main directly (`CLAUDE.md`).

---

## Dependency across phases

```
0 plan
  → 1 truth + pins + doctor honesty
    → 2 SSRF / cookie-docs / --system / xhs flags
      → 3 keychain + twitter path
        → 4 gh read-only + channel gating
          → 5 release
```

Do not skip 2 to get to 4. Do not put keychain in 1. Do not rewrite channels in any phase unless Phase 2's "stop fetching" option requires deleting `read()` helpers.

## Branching

New branch per phase (or per finding cluster). PR to main. Never push to main. `pytest tests/ -v` green before commit. Pepe asks for the commit; do not commit unprompted.
