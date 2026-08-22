# F3 Doctor honesty

**Parent:** none · **Phase:** 1 (prose + schema lock) · **Status:** phase-1 done (F3.2 blocked) · **Audit:** doctor-false-neg

Doctor must be a signal agents can trust **without** running cookie-refreshing CLIs and **without** adding a JSON field in Phase 1.

Today `check_all` returns per channel (`doctor.py:37-44`): `status`, `name`, `message`, `tier`, `backends`, `active_backend`. `status` ∈ `{ok, warn, off, error}` (`base.py:64`, `tests/test_channel_contracts.py`).

CLI: `agent-reach doctor` / `doctor --json` (`cli.py:131-133`, `cli.py:1972-1979`).

Never weaken `tests/test_doctor_credential_boundaries.py`.

---

## F3.1 Login-channel false-negatives, prose

- **Parent:** F3
- **Phase:** 1
- **Status:** planned
- **Goal:** Humans and agents stop reading `warn` + `active_backend: null` as "this backend is off".
- **Files:**
  - `agent_reach/doctor.py` `format_report` legend (`:62`, `:103` `ok_count/total 个渠道可用`)
  - `agent_reach/skill/SKILL.md:32-35` (already explains null ≠ absence)
  - `agent_reach/skill/SKILL_en.md:30-34` (same)
  - `docs/install.md` doctor notes (`:375` area)
- **Acceptance:**
  - Text report legend distinguishes: live-ok vs installed/configured but unverified vs missing. Do not remap github/twitter/xhs/reddit/opencli/exa/linkedin `warn` → `ok`.
  - `ok_count/total 个渠道可用` must not imply the other channels are broken. Rephrase to "N live-ok; others may be configured and unverified".
  - Skill standing rule stays: only live-probe when the user task needs that platform; follow references; do not treat null as missing.
  - Dual-language skill both updated.
- **Tests:** F11.2: `format_report` fixture in `tests/test_doctor.py` still parses; update expected strings if the legend changes. Cookie-boundary tests unchanged. Optional: a unit test that a github-like `warn` result is not counted as "off" in the summary sentence.
- **Dependencies:** F3.3, F3.4
- **Risks:** agents parsing **text** report (not JSON) may break on legend wording. JSON schema stays identical (F3.3).
- **Approval needed?** no. Do not add keys.

---

## F3.2 `doctor --json` `confidence` field

- **Parent:** F3
- **Phase:** 1 originally; **skipped this execute**
- **Status:** **blocked-on-Pepe**
- **Goal:** Machine-readable `confidence: live | configured | installed | missing` as specified in `ENGINEERING.md`.
- **Files (when unblocked):** `agent_reach/doctor.py:37-44`, `tests/test_doctor.py:53-78` (exact dict equality on keys), `tests/test_cli.py` doctor JSON mock (`:36-42`), skill docs that describe JSON.
- **Acceptance (when approved):** additive field only. Existing keys unchanged. `status` enum unchanged. Mapping in ENGINEERING.md. Never run `twitter status` / `gh auth status` / live MCP to promote `live`.
- **Tests:** update `test_doctor.py` exact dict; contract test that every result has `confidence` in the enum.
- **Dependencies:** Pepe yes. F3.1 is the Phase 1 substitute.
- **Risks:** public API. Agents that iterate keys are fine (additive); agents that assume a closed schema of six keys need the field documented.
- **Approval needed?** **yes.** Public API. **Phase 1: do not implement.** Leave a comment in the Phase 1 PR that F3.2 remains blocked.

Proposed mapping (do not ship until approved):

| Example | status (keep) | confidence (add) |
|---------|---------------|------------------|
| web always | ok | live |
| youtube yt-dlp works | ok | live |
| gh present + hosts.yml | warn | configured |
| gh present, no auth | warn | installed |
| twitter cookies in YAML, no status probe | warn | configured |
| mcporter + exa server name | warn | configured |
| missing binary | off/warn as today | missing |

---

## F3.3 JSON schema freeze (`status` enum)

- **Parent:** F3
- **Phase:** 1
- **Status:** planned (lock)
- **Goal:** Phase 1 does not break `doctor --json` consumers.
- **Files:** `doctor.py:37-44`, `tests/test_doctor.py`, `tests/test_channel_contracts.py:35`.
- **Acceptance:** Result dict keys remain exactly `status`, `name`, `message`, `tier`, `backends`, `active_backend`. `status` remains `ok|warn|off|error`. No new keys. No removed keys. Message strings may change (F3.1).
- **Tests:** extend `test_check_all_collects_channel_results` or add `test_doctor_json_keys_stable` that asserts `set(result.keys()) == {those six}` for every channel from a real `check_all` (with probes mocked if needed).
- **Dependencies:** none
- **Risks:** F3.1 message edits. That is allowed.
- **Approval needed?** no

---

## F3.4 Document which channels can never be `ok`

- **Parent:** F3
- **Phase:** 1
- **Status:** planned
- **Goal:** Operators know 8 channels never return `ok` by design, not by failure.
- **Files:** `product/CHANNELS.md` (already has the table), `agent_reach/skill/SKILL.md` / `SKILL_en.md` (short list), `docs/install.md` doctor section. Channel `check()` implementations:
  - Never ok (refuse live probe): `github.py`, `twitter.py`, `xiaohongshu.py`, `reddit.py`, `_opencli_site.py` (facebook/instagram), `exa_search.py`, `linkedin.py`
  - Can ok: `web.py`, `youtube.py`, `rss.py`, `bilibili.py`, `v2ex.py`, `xueqiu.py`, `xiaoyuzhou.py`
- **Acceptance:** Skill or install.md lists the never-ok names and says "warn means unverified, not off". CHANNELS.md table stays the source of truth; do not invent a 16th channel.
- **Tests:** F11.2 optional parametrize: with creds present and network blocked, those eight still return `warn` not `ok`. Prefer extending existing channel tests over live probes.
- **Dependencies:** F1.11 (zero-config wording)
- **Risks:** listing in skill makes the skill longer. Keep a 4-line note, not a second CHANNELS.md.
- **Approval needed?** no

---

## F3.5 `watch` treats all `warn` as issues

- **Parent:** F3
- **Phase:** 2
- **Status:** planned
- **Goal:** `agent-reach watch` (`cli.py:2284-2327`) stops treating by-design `warn` as "not 全部正常".
- **Files:** `agent_reach/cli.py:_cmd_watch` (`:2302-2306` currently appends every `warn` to `issues`, so github configured still prints `[!]`).
- **Acceptance:** `watch` reports `off`/`error` as issues. By-design unverified `warn` is not an issue, or is a separate "unverified" line that does not block the healthy summary. Do not call this a JSON schema change.
- **Tests:** unit test with stub results: web ok + github warn → watch can report healthy-enough, not a pile of `[!]`.
- **Dependencies:** F3.1, F3.4. Not Phase 1 (`ENGINEERING.md`: Phase 1 docs, behavior stays).
- **Risks:** users who used `watch` as "nudge me to configure twitter" lose that nudge. Acceptable; doctor text still lists them.
- **Approval needed?** no (output of a diagnostics command, not `doctor --json` schema). Still Phase 2 so Phase 1 stays docs-first.
