# F5 SSRF / fetch

**Parent:** none · **Phase:** 2 · **Status:** planned · **Audit:** dns-rebinding, owned-fetchers, rss-substring

Agent Reach is not a fetcher. Three modules still speak HTTP inside this repo: `web.py`, `v2ex.py`, `xueqiu.py`. `transcribe.py` hands URLs to yt-dlp after a literal-IP check. Current guard: `utils/url.py` `normalize_public_http_url` rejects private **literal** IPs and a small host denylist, then **skips DNS** (`url.py:47-84`; `transcribe.py:214-247`).

ADR-008: either DNS-pin to global unicast, or stop in-process fetch. Pepe picks before code.

Do not export `AgentReach.read`. `WebChannel.read` is unused by `core.py`.

---

## F5.1 DNS-pin helper vs stop in-process fetch

- **Parent:** F5
- **Phase:** 2
- **Status:** **blocked-on-Pepe**
- **Goal:** Hostname rebinding cannot send our fetchers (or our pre-check) to `169.254.169.254` / loopback / RFC1918.
- **Files:** `agent_reach/utils/url.py` (extend or add helper), callers listed in F5.2–F5.5. Mechanism notes in `ENGINEERING.md` SSRF helper.
- **Acceptance:** One mechanism, applied everywhere we still fetch or pre-check:
  1. **Pin:** `getaddrinfo` → every A/AAAA must be global unicast (`ipaddress`: not private, loopback, link-local, reserved, multicast, unspecified, not documentation). Fail closed if any address is bad. Prefer connect-to-pinned-IP with original SNI/Host for **our** urllib. Honest TOCTOU if we still pass a hostname to yt-dlp after a successful resolve: document it; still reject bad first-hop DNS.
  2. **Stop:** delete in-process clients; skill uses `curl` / yt-dlp. Residual SSRF moves to those binaries. If we still wrap them, pin before exec.
- **Tests:** `tests/test_dns_pin.py` (new): fake `getaddrinfo`. Hostname → RFC1918 / link-local / metadata IP rejected. Global unicast allowed. Existing `tests/test_url_security.py` (`host_matches`) still passes.
- **Dependencies:** Pepe pick. Do not ship a half-pin that still hands a hostname to yt-dlp and calls it done unless the pick is "stop" for those paths.
- **Risks:** IPv6 / dual-stack / Happy Eyeballs. Fail closed if **any** address is bad. Do not add runtime deps.
- **Approval needed?** **yes.** Mechanism. New helper is internal unless exported (do not export).

---

## F5.2 `WebChannel.read`

- **Parent:** F5
- **Phase:** 2
- **Status:** planned
- **Goal:** Jina fetch is either pinned or gone from Python.
- **Files:** `agent_reach/channels/web.py:48-67` (`urllib` to `r.jina.ai` after `normalize_public_http_url`). `can_handle` is always True (`:40-41` area). `check()` always ok, no network. Skill already uses `curl -s "https://r.jina.ai/URL"` (`SKILL.md:64`). `tests/test_web_channel.py`.
- **Acceptance:**
  - If pin: `read()` goes through the helper. Tests with fake resolver.
  - If stop: delete or stop calling `read()`. Update `test_web_channel.py`. Do not add `AgentReach.read`. `check()` stays always-ok (no network).
- **Tests:** web channel tests updated. `test_core.py` still doctor-only.
- **Dependencies:** F5.1
- **Risks:** deleting a public-ish method on `WebChannel`. Unused by `AgentReach`, but it is a class method.
- **Approval needed?** **yes** if deleting `WebChannel.read`. no if only pinning internally.

---

## F5.3 V2EX owned fetch

- **Parent:** F5
- **Phase:** 2
- **Status:** planned
- **Goal:** V2EX public JSON is pinned or moved to skill curl.
- **Files:** `agent_reach/channels/v2ex.py`, `tests/test_v2ex_channel.py`, skill V2EX curl (`SKILL.md:72-73`, `User-Agent: agent-reach/1.0`).
- **Acceptance:** Same pin-or-stop as F5.1. Extended channel, not commercial headline (`CHANNELS.md`). Hardcoded HTTPS stays; still pin DNS.
- **Tests:** existing v2ex tests + fake resolver if we keep Python fetch.
- **Dependencies:** F5.1
- **Risks:** V2EX TLS / CDN IPs that look "shared". Fail closed on non-global unicast only, not on CDN.
- **Approval needed?** no (follows F5.1)

---

## F5.4 Xueqiu owned fetch + CookieJar

- **Parent:** F5
- **Phase:** 2 (pin/stop) · jar remains power-user
- **Status:** planned
- **Goal:** Xueqiu HTTP cannot rebind. Process-global jar is not the product path.
- **Files:** `agent_reach/channels/xueqiu.py` (CookieJar around `:24-28`, stock APIs), `tests/test_xueqiu_channel.py`.
- **Acceptance:** Fetch through pin helper or stop. Do not make `xq_a_token` commercial. `--from-browser` for xueqiu stays power-user (F4.5).
- **Tests:** xueqiu tests + DNS-pin cases if fetch remains.
- **Dependencies:** F5.1, F8.3
- **Risks:** pinning may break if Xueqiu uses weird DNS. Fail closed.
- **Approval needed?** no (follows F5.1)

---

## F5.5 yt-dlp / transcribe URL checks

- **Parent:** F5
- **Phase:** 2
- **Status:** planned
- **Goal:** `transcribe` does not pass a rebinding hostname through a literal-IP-only check.
- **Files:** `agent_reach/transcribe.py:214-247` (literal IP + denylist), `:250-270` (hands URL to yt-dlp). `agent_reach/cli.py` `transcribe` subcommand. `tests/test_transcribe.py`. YouTube channel `channels/youtube.py` does not fetch; captions are yt-dlp from the skill.
- **Acceptance:** Apply F5.1 before exec. If pin cannot bind yt-dlp to an IP+Host, document residual TOCTOU and still reject bad first resolve. Do not disable transcribe.
- **Tests:** fake resolver in transcribe tests. Existing provider tests stay.
- **Dependencies:** F5.1
- **Risks:** yt-dlp may ignore IP+Host. Then the honest bar is first-hop reject + docs, or stop wrapping URL transcribe and require a local file.
- **Approval needed?** no (follows F5.1). Ask if you would remove URL transcribe.

---

## F5.6 RSS substring `can_handle`

- **Parent:** F5
- **Phase:** 2
- **Status:** planned
- **Goal:** Unused matcher is not a future host-lookalike bug.
- **Files:** `agent_reach/channels/rss.py:13-14` (`"/feed", "/rss", ".xml", "atom"` substring). Core does not route on it (`core.py` doctor-only). Skill parses with feedparser (`skill/references/web.md`).
- **Acceptance:** Switch to `host_matches` where a host is known, or a tighter heuristic that does not match `evil.com/notxml` / lookalikes; **or** document unused and add a test that `AgentReach` does not dispatch `can_handle` into fetch. Prefer tightening while unused.
- **Tests:** `tests/test_channel_contracts.py` `can_handle` sample for rss stays. Add negatives for lookalikes if you tighten.
- **Dependencies:** none (can ship even if F5.1 is still blocked)
- **Risks:** over-tight matching breaks legitimate `/feed.xml` URLs. Doctor does not use `can_handle`.
- **Approval needed?** no
