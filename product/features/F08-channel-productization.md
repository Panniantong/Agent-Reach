# F8 Channel productization

**Parent:** none · **Phase:** 1 (docs: commercial first) and 4 (install gating) · **Status:** planned

Registry stays 15 names. No deletions in Phases 1–4 unless Pepe asks. Gating is skill + install + docs.

Commercial core (the product): `github`, `exa_search`, `youtube`, `web`, `rss`.

Extended (keep, not headline): `v2ex`, `bilibili` (search), `xiaoyuzhou`.

Power-user / burner: `twitter`, `xiaohongshu`, `reddit`, `facebook`, `instagram`, `xueqiu`, LinkedIn MCP.

Source of truth: `product/CHANNELS.md`. Registry: `agent_reach/channels/__init__.py:26-42`.

---

## F8.1 Commercial set first in README / skill

- **Parent:** F8
- **Phase:** 1 (docs) · 4 (skill structure)
- **Status:** planned
- **Goal:** Default story is official APIs / public CLIs.
- **Files:** `README.md` platform table, `docs/README_en.md` (and JA/KO if they copy the table), `agent_reach/skill/SKILL.md` zero-config block (`:59-77`) vs login block (`:79-106`). Phase 4: move cookie/OpenCLI commands under a "power user / burner" heading.
- **Acceptance:**
  - **Phase 1:** commercial five named first in README; cookie rows labeled. Skill quick commands can keep V2EX/Bilibili (extended, public) but must not lead with Twitter/XHS cookies. F1.2 + F1.3 overlap.
  - **Phase 4:** skill routing table: commercial commands in the zero-config block; cookie platforms in a gated section with burner warning (README already warns `:262`).
- **Tests:** Phase 1: F1.2 tests. Phase 4: skill grep that Twitter/XHS examples live under a power-user heading.
- **Dependencies:** F1.2, F1.3. Phase 4 depends on F7.1.
- **Risks:** skill gets longer. Prefer headings, not a second skill.
- **Approval needed?** no for Phase 1 docs. Phase 4 skill reorder is policy; include it in the Phase 4 ask along with F7.1.

---

## F8.2 `--channels=all` vs explicit names

- **Parent:** F8
- **Phase:** 4
- **Status:** **blocked-on-Pepe**
- **Goal:** Default `--system` does not silently install cookie platforms; `--channels=all` is loud.
- **Files:** `cli.py:93-96` (`--channels` help: `twitter,xiaoyuzhou,xueqiu,xiaohongshu,reddit,facebook,instagram,bilibili,linkedin,all`). `CHANNEL_INSTALLERS` `cli.py:265-277`: twitter, xiaoyuzhou, xiaohongshu, reddit, facebook, instagram, bilibili, opencli. Xueqiu and linkedin are cookie/manual (no installer). Empty `--channels` already does not auto-install twitter/xhs (`cli.py:450-455` hints after `--system`).
- **Acceptance:**
  - Default `--system` installs commercial core tools (gh / mcporter / yt-dlp / skill) only. Cookie platforms require explicit names.
  - `--channels=all` prints a burner warning and then may install optional installers. Pepe picks whether `all` includes cookie platforms or only extended (bilibili, xiaoyuzhou, opencli).
  - Help text distinguishes commercial vs power-user.
- **Tests:** install `--dry-run --system` without `--channels` does not call twitter/xhs installers. `--channels=all --dry-run` stdout contains a burner warning.
- **Dependencies:** Pepe pick on `all` meaning.
- **Risks:** users who script `--channels=all` get a new warning (OK) or a behavior change if `all` stops including twitter. That is why we ask.
- **Approval needed?** **yes.**

---

## F8.3 Per-channel keep / API / power-user

- **Parent:** F8
- **Phase:** 4 (docs already in CHANNELS.md; install/skill enforce)
- **Status:** planned
- **Goal:** Every registered channel has a disposition and nobody deletes it "to clean up".
- **Files:** `product/CHANNELS.md` table (source). Channel modules listed there. Bird CLI already labeled legacy in `twitter.py:37`. xhs-cli is a fallback in XHS backends.
- **Acceptance:**
  - Keep = stays in `ALL_CHANNELS`.
  - Official-API / public CLI = commercial or extended.
  - Power-user = stays, gated.
  - Deprecate ≠ delete in this conversion. Stop marketing bird / xhs-cli. Do not remove from ordered backends without asking.
- **Tests:** F1.10 count stays 15 unless Pepe asks to add/remove.
- **Dependencies:** F8.1, F8.2
- **Risks:** someone "helpfully" drops facebook. Do not.
- **Approval needed?** no (no deletions). yes to delete any channel.

Per-channel (must not invent files):

| Channel | File | Class | Phase notes |
|---------|------|-------|-------------|
| github | `channels/github.py` | Commercial | F3 honesty, F7 wrap |
| exa_search | `channels/exa_search.py` | Commercial | Doctor configured vs missing; no live MCP |
| youtube | `channels/youtube.py` | Commercial | F5.5 transcribe URLs |
| web | `channels/web.py` | Commercial | F5.2 |
| rss | `channels/rss.py` | Commercial | F5.6 matcher; skill feedparser |
| v2ex | `channels/v2ex.py` | Extended | F5.3 |
| bilibili | `channels/bilibili.py` | Extended | search public; OpenCLI subs power-user |
| xiaoyuzhou | `channels/xiaoyuzhou.py` | Extended | Whisper keys → F6 |
| linkedin | `channels/linkedin.py` | Split | F8.4 |
| twitter | `channels/twitter.py` | Power-user | F4.4, F4.5 |
| xiaohongshu | `channels/xiaohongshu.py` | Power-user | F4.3 |
| reddit | `channels/reddit.py` | Power-user | no zero-config |
| facebook | `channels/facebook.py` + `_opencli_site.py` | Power-user | gated |
| instagram | `channels/instagram.py` + `_opencli_site.py` | Power-user | gated |
| xueqiu | `channels/xueqiu.py` | Power-user | F5.4 |

`channels/mcporter.py` is a helper, not a 16th channel.

---

## F8.4 LinkedIn split (Jina vs MCP login)

- **Parent:** F8
- **Phase:** 4
- **Status:** planned
- **Goal:** Public LinkedIn pages are commercial-adjacent (Web/Jina). MCP browser login is power-user.
- **Files:** `channels/linkedin.py`, `skill/references/career.md`, README LinkedIn row if any.
- **Acceptance:** Skill career.md: default is Jina/web for public pages. `mcp-server-linkedin` is gated with the same burner/session warning as other cookie platforms. Doctor still does not start uvx for LinkedIn.
- **Tests:** skill grep: career.md does not present MCP browser login as the default commercial path.
- **Dependencies:** F8.1
- **Risks:** none
- **Approval needed?** no
