# F1 Contract truth

**Parent:** none · **Phase:** 1 · **Status:** planned · **Audit:** contract-drift (low)

Stop the docs from lying about what the code is. After F1, a new agent reading CLAUDE.md / README / skill / CONTRIBUTING can implement against reality: 15 channels, `can_handle` + `check`, doctor-only core, YAML config, curated backends not "the entire internet".

Do not bump version. Do not change CLI flags, doctor JSON keys, or auth.

---

## F1.1 CLAUDE.md contract + count

- **Parent:** F1
- **Phase:** 1
- **Status:** planned
- **Goal:** `CLAUDE.md` matches the registry and `base.py`.
- **Files:** `CLAUDE.md`
- **Acceptance:**
  - Project line says 15 platforms, not 13.
  - Structure line for `core.py` says installer/doctor/config (doctor-only), not "read/search routing logic".
  - Channel contract line lists `can_handle(url)` and `check()` only. No required `read`/`search`.
  - Conventions still say one file per channel inheriting from `Channel` in `base.py` (today it wrongly says `BaseChannel`).
  - Version rule still names three places; the third place is the test that **asserts** equality (see F1.5), not fixture data.
- **Tests:** F11.1 grep: `CLAUDE.md` must not contain `13 internet platforms` or `13 platforms`. Must not require `read(url)` / `search(query)` as the channel contract.
- **Dependencies:** F1.5 (third version locus must be a real assert).
- **Risks:** Contributors who memorized the old contract. Low.
- **Approval needed?** no

---

## F1.2 README commercial story + `product/` pointer

- **Parent:** F1
- **Phase:** 1
- **Status:** planned
- **Goal:** Homepage still sells the installer, but the commercial set is first, GitHub writes are not the unlock, and `product/` is findable.
- **Files:** `README.md` (marketing homepage). Optionally a one-line pointer only; do not turn README into a docs index.
- **Acceptance:**
  - A visible pointer to `product/README.md` (设计理念 section or a short "Productization" line). Encoded YES (ADR-017).
  - Platform table GitHub row (`README.md:112` today) must not list 提 Issue/PR、Fork as the supported unlock. Read/search only.
  - Cookie platforms stay in the table but labeled power-user / burner (full gating copy can wait for F8.1/F8.3). Minimum: do not lead with them as the product.
  - Check-only default and `--system` warning stay.
- **Tests:** F11.1 grep: `README.md` GitHub row does not contain `gh issue create` / `Fork` as a feature unlock. Pointer path `product/README.md` exists in README.
- **Dependencies:** none
- **Risks:** Chinese marketing rewrite can sprawl. Keep the smallest viable edit: pointer + GitHub row + do not claim entire-internet as the product. Full rewrite of the hero ("一键装上互联网能力") is allowed if it is one sentence, not a redesign.
- **Approval needed?** no. README pointer is encoded YES. Full Chinese rewrite of every section is out of Phase 1; commercial-table + pointer + GitHub row is in.

---

## F1.3 Skill dual-language cookie-paste line

- **Parent:** F1 (overlaps F4 / F12)
- **Phase:** 1
- **Status:** planned
- **Goal:** Skill stops telling agents the user should hand cookies to the agent.
- **Files:**
  - `agent_reach/skill/SKILL.md:142` (`用户只需提供 cookies，其他配置由 agent 完成。`)
  - `agent_reach/skill/SKILL_en.md:152` (`The user only provides cookies / one extension click; the agent does the rest.`)
- **Acceptance:**
  - Both files: that happy-path sentence is gone.
  - Replacement (if any) points at Cookie-Editor export **piped to** `agent-reach configure twitter-cookies --stdin` / `xhs-cookies --stdin` or a local TTY getpass. Never "paste to your agent".
  - Cookie-refresh explanation (`SKILL.md:81-88`, `SKILL_en.md` Twitter boundary) stays.
  - `cli.py:479-488` locale pick copies `SKILL.md` or `SKILL_en.md` into target `SKILL.md`. Change **both** sources.
- **Tests:** F11.1 grep both skill files for `用户只需提供 cookies` and `The user only provides cookies`. Must be zero. Do not grep so broadly that "cookies" in the Twitter boundary paragraph fails.
- **Dependencies:** none. Full `docs/cookie-export.md` rewrite is F4.1 (Phase 2).
- **Risks:** Already-copied skills under `~/.claude/skills/agent-reach/` etc. do not update until `--system` or `skill --install`. Mention in the Phase 1 PR body. `cli.py:500-501` preserves existing skill dirs unless force.
- **Approval needed?** no

---

## F1.4 CONTRIBUTING registry truth

- **Parent:** F1
- **Phase:** 1
- **Status:** planned
- **Goal:** New-channel instructions match auto-discovery.
- **Files:** `CONTRIBUTING.md` English "Adding New Channels" (`:50-58`) and Chinese "添加新渠道" (`:101-107`)
- **Acceptance:**
  - Drop "Update `agent_reach/doctor.py` to include the new channel". Doctor iterates `get_all_channels()` (`doctor.py:16-23`).
  - Say: add the class to `agent_reach/channels/<name>.py`, instantiate it in `ALL_CHANNELS` in `agent_reach/channels/__init__.py`, implement `can_handle` + `check`, add tests, update `product/CHANNELS.md` and the README table.
  - Do not tell people to implement `read`/`search`.
- **Tests:** F11.1 grep `CONTRIBUTING.md` for `doctor.py` in the add-channel section. Must not instruct updating doctor.py.
- **Dependencies:** F1.1
- **Risks:** none
- **Approval needed?** no

---

## F1.5 Version three-place assert

- **Parent:** F1
- **Phase:** 1
- **Status:** planned
- **Goal:** The third version locus actually asserts.
- **Files:**
  - `pyproject.toml:3` (`version = "1.5.0"`) — read, do not bump
  - `agent_reach/__init__.py:4` (`__version__ = "1.5.0"`) — read, do not bump
  - `tests/test_cli.py` (today uses `1.5.0` only as update-comparison fixture, e.g. `:362`, `:401-412`) **or** new `tests/test_docs_contract.py`
  - `CLAUDE.md` version-rule line must name the file that contains the assert
- **Acceptance:**
  - A test reads `pyproject.toml` `[project].version` and asserts `agent_reach.__version__ ==` that string.
  - Current version remains `1.5.0`. Phase 1 is not a release (F10).
  - If the assert lives in a new module, CLAUDE.md's "three places" line names that module, not a file that only has fixture data.
- **Tests:** the assert itself. Existing `test_cli.py` update-comparison fixtures keep using literal `1.5.0` as **input data** (that is fine; they are not the contract).
- **Dependencies:** none
- **Risks:** tomllib vs tomli on 3.10. Prefer reading pyproject with `tomllib` (3.11+) or a tiny parser; or regex `^version = "([^"]+)"` under `[project]`. Do not add a runtime dep. Dev extra already has pytest.
- **Approval needed?** no

---

## F1.6 `config.json` → `config.yaml` in install docs

- **Parent:** F1
- **Phase:** 1
- **Status:** planned
- **Goal:** Install docs name the file that `config.py` actually writes.
- **Files:** `docs/install.md:42` (`~/.agent-reach/config.json`). Grep the rest of `docs/` and `agent_reach/guides/` for `config.json`.
- **Acceptance:** Every Agent Reach config-file path in those docs is `~/.agent-reach/config.yaml`. `Config.CONFIG_DIR` / `config.yaml` (`config.py`, `doctor.py:118`).
- **Tests:** F11.1 grep `docs/` and `agent_reach/guides/` for `config.json` referring to Agent Reach config. Zero matches. (Do not fail on unrelated JSON such as mcporter config.)
- **Dependencies:** none
- **Risks:** false-positive grep on `config/mcporter.json`. Scope the pattern to `~/.agent-reach/config.json` or `config.json` in install.md tables.
- **Approval needed?** no

---

## F1.7 pyproject `description` wording

- **Parent:** F1
- **Phase:** 1
- **Status:** planned
- **Goal:** Packaging description matches the product: curated backends, not "entire internet" / "10+".
- **Files:** `pyproject.toml:4` only (`description = "Give your AI Agent eyes to see the entire internet. Search + Read 10+ platforms."`)
- **Acceptance:**
  - Description is one or two sentences: local-first installer + doctor + skill for a curated set of read/search backends (15 registered; commercial core GitHub / Exa / YouTube / RSS / Jina).
  - Do not change `version`, `keywords`, `classifiers`, dependencies, optional extras, or scripts.
  - Do not publish to PyPI. Do not bump version. This is repo text, not a release (F10).
- **Tests:** F11.1: `pyproject.toml` description must not contain `entire internet` or `10+`.
- **Dependencies:** none
- **Risks:** The string is what a future PyPI page would show. That is why F10 still asks before publish. Editing it in git without a version bump is the Phase 1 contract fix.
- **Approval needed?** Encoded YES for description/readme text only. NO if you would bump version or change other metadata. Stay on `:4`.

---

## F1.8 Kill "entire internet" in package strings

- **Parent:** F1
- **Phase:** 1
- **Status:** planned
- **Goal:** User-visible Python strings match F1.7.
- **Files:**
  - `agent_reach/__init__.py:2` module docstring
  - `agent_reach/core.py:24` `AgentReach` class docstring
  - `agent_reach/cli.py:64` argparse `description=`
- **Acceptance:** None of those three still say "entire internet". Wording can match F1.7 (curated backends / installer + doctor). Do not rename `AgentReach`, do not add methods, do not change argparse flags.
- **Tests:** F11.1 grep those three files for `entire internet`. Zero.
- **Dependencies:** F1.7 (same claim)
- **Risks:** argparse description is user-visible (`agent-reach --help`). Not a flag change. Not public API.
- **Approval needed?** no

---

## F1.9 Translation README taglines

- **Parent:** F1
- **Phase:** 1
- **Status:** planned
- **Goal:** English/JA/KO homepages do not keep the claim we kill in README.
- **Files:**
  - `docs/README_en.md:4` (`one-click access to the entire internet`)
  - `docs/README_ja.md` / `docs/README_ko.md` equivalent hero lines (inspect; sync if they repeat the claim)
- **Acceptance:** Tagline matches the Chinese README after F1.2 (curated / installer, not entire internet). GitHub write unlocks, if present in those tables, same fix as F1.2.
- **Tests:** F11.1 grep `docs/README_en.md` for `entire internet`. Zero. If JA/KO have an obvious equivalent, include them.
- **Dependencies:** F1.2
- **Risks:** Translation drift. DIRECTORY.md already says: if we touch README, sync translations in the same PR. Do not rewrite the whole JA/KO pages.
- **Approval needed?** no

---

## F1.10 Registry count test `== 15`

- **Parent:** F1
- **Phase:** 1
- **Status:** planned
- **Goal:** Channel count cannot silently drift from the documented 15.
- **Files:** `tests/test_channel_contracts.py` (`test_channel_registry_contract` today asserts unique names, not length). `agent_reach/channels/__init__.py:26-42`.
- **Acceptance:** `assert len(get_all_channels()) == 15`. When someone adds a channel, this test fails until they bump the number **and** update CLAUDE.md / CHANNELS.md. That is intended.
- **Tests:** the assert. Existing uniqueness assert stays.
- **Dependencies:** none
- **Risks:** Hard-coded 15 will need a bump when Pepe adds a channel later. That is the point.
- **Approval needed?** no

---

## F1.11 Skill "zero-config" count honesty

- **Parent:** F1
- **Phase:** 1
- **Status:** planned
- **Goal:** Skill frontmatter does not invent a zero-config count that conflicts with the commercial set.
- **Files:** `agent_reach/skill/SKILL.md:14` and `SKILL_en.md:13` (`Zero config for 6 channels`).
- **Acceptance:** Either name the actual zero-config / always-ok set from code (today doctor can `ok`: web, youtube, rss, bilibili, v2ex, xueqiu, xiaoyuzhou = 7, and xueqiu is power-user) **or** drop the numeric claim and say "run `doctor --json`". Do not say 6 if the code says otherwise. Prefer: "15 registered channels; commercial core does not need session cookies."
- **Tests:** F11.1: skill files do not contain `Zero config for 6` unless 6 is still accurate after you verify `tier==0` and `check` can return `ok` without creds. Inspect `channels/*.py` `tier` before writing the sentence.
- **Dependencies:** F3.4 (which channels can `ok`)
- **Risks:** Over-fitting a number that doctor honesty will refine. Safer to drop the number.
- **Approval needed?** no

---

## Parent acceptance

All F1.* Phase 1 items merged. `pytest tests/ -v` green. Version still `1.5.0`. No new runtime deps. No doctor JSON key added.
