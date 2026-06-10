<h1 align="center">👁️ Agent Reach</h1>

<p align="center">
  <strong>AI 에이전트가 인터넷 전체에 접근할 수 있도록 한 번에 설정해 드립니다</strong>
</p>

<p align="center">
  <a href="../LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue.svg?style=for-the-badge" alt="MIT License"></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.10+-green.svg?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.10+"></a>
  <a href="https://github.com/Panniantong/agent-reach/stargazers"><img src="https://img.shields.io/github/stars/Panniantong/agent-reach?style=for-the-badge" alt="GitHub Stars"></a>
</p>

<p align="center">
  <a href="#빠른-시작">빠른 시작</a> · 한국어 · <a href="../README.md">中文</a> · <a href="README_en.md">English</a> · <a href="README_ja.md">日本語</a> · <a href="#지원-플랫폼">지원 플랫폼</a> · <a href="#설계-철학">설계 철학</a>
</p>

---

## Agent Reach가 필요한 이유

AI 에이전트는 이미 인터넷에 접근할 수 있습니다 — 하지만 "인터넷에 접속할 수 있다"는 것은 시작에 불과합니다.

가장 가치 있는 정보는 소셜 미디어와 특화된 플랫폼에 분포되어 있습니다: Twitter 토론, Reddit 피드백, YouTube 튜토리얼, XiaoHongShu 리뷰, Bilibili 비디오, GitHub 활동... **여기가 정보 밀도가 가장 높은 곳**이지만, 각 플랫폼은 고유한 진입장벽이 있습니다:

| 문제점 | 현실 |
|------------|---------|
| Twitter API | 유료 사용, 중간 정도 사용량 ~월 $215 |
| Reddit | 서버 IP가 403 오류 발생 |
| XiaoHongShu | 둘러보기 위해 로그인 필요 |
| Bilibili | 해외/서버 IP 차단 |

에이전트를 이 플랫폼에 연결하려면 도구를 찾고, 의존성을 설치하고, 설정을 디버깅해야 합니다 — 하나씩 직접.

**Agent Reach는 이를 하나의 명령으로 바꿉니다:**

```
Install Agent Reach: https://raw.githubusercontent.com/Panniantong/agent-reach/main/docs/install.md
```

이 명령을 에이전트에 복사해서 붙여넣으세요. 몇 분 뒤에는 트윗을 읽고, Reddit을 검색하고, Bilibili를 볼 수 있게 됩니다.

**이미 설치하셨나요? 한 번에 업데이트하세요:**

```
Update Agent Reach: https://raw.githubusercontent.com/Panniantong/agent-reach/main/docs/update.md
```

### ✅ 시작하기 전에 알면 좋은 것들

| | |
|---|---|
| 💰 **완전 무료** | 모든 도구는 오픈 소스, 모든 API는 무료입니다. 유일한 비용은 서버 프록시(월 $1)일 수 있습니다 — 로컬 컴퓨터에서는 불필요 |
| 🔒 **프라이버시 안전** | Cookie는 로컬에 유지됩니다. 업로드되지 않습니다. 완전 오픈 소스 — 언제든지 감사 가능 |
| 🔄 **최신 상태 유지** | 업스트림 도구(yt-dlp, twitter-cli, rdt-cli, Jina Reader 등)를 추적하고 정기적으로 업데이트 |
| 🤖 **모든 에이전트와 호환** | Claude Code, OpenClaw, Cursor, Windsurf... 명령을 실행할 수 있는 모든 에이전트 |
| 🩺 **내장 진단 도구** | `agent-reach doctor` — 하나의 명령으로 작동 항목, 작동하지 않는 항목, 수정 방법 표시 |

---

## 지원 플랫폼

| 플랫폼 | 기능 | 설정 | 참고 |
|----------|-------------|:-----:|-------|
| 🌐 **Web** | 읽기 | 없음 | 모든 URL → 깨끗한 Markdown ([Jina Reader](https://github.com/jina-ai/reader) ⭐9.8K) |
| 🐦 **Twitter/X** | 읽기 · 검색 | Cookie | Cookie로 검색, 타임라인, 트윗 읽기, 아티클 읽기 가능 ([twitter-cli](https://github.com/public-clis/twitter-cli)) |
| 📕 **XiaoHongShu** | 읽기 · 검색 · **게시글 작성 · 댓글 · 좋아요** | Cookie | `pipx install xiaohongshu-cli` + `xhs login` ([xhs-cli](https://github.com/jackwener/xiaohongshu-cli)) |
| 🎵 **Douyin** | 비디오 파싱 · 워터마크 없는 다운로드 | mcporter | [douyin-mcp-server](https://github.com/yzfly/douyin-mcp-server) 통해, 로그인 불필요 |
| 💼 **LinkedIn** | Jina Reader (공개 페이지) | Cookie | 전체 프로필, 회사, 채용 공고 검색 가능. 에이전트에 "LinkedIn 설정 도와줘"라고 말하세요 |
| 💬 **WeChat Articles** | 검색 + 읽기 | 없음 | Exa를 통한 WeChat 공식 계정 게시글 검색 + 읽기 (설정 없음) + 선택적 [Camoufox](https://github.com/daijro/camoufox) |
| 📰 **Weibo** | 인기 · 검색 · 피드 · 댓글 | 없음 | 핫 검색, 콘텐츠/사용자/주제 검색, 피드, 댓글 ([mcp-server-weibo](https://github.com/Panniantong/mcp-server-weibo)) |
| 💻 **V2EX** | 인기 주제 · 노드 주제 · 주제 상세 + 답글 · 사용자 프로필 | 없음 | 공개 JSON API, 인증 없음. 기술 커뮤니티 콘텐츠에 적합 |
| 📈 **Xueqiu (雪球)** | 주식 시세 · 검색 · 인기 글 · 인기 종목 | 브라우저 Cookie | 에이전트에 "Xueqiu 설정 도와줘"라고 말하세요 |
| 🎙️ **Xiaoyuzhou Podcast** | 음성 변환 | 무료 API key | Groq Whisper를 통한 팟캐스트 오디오 → 전체 텍스트 변환 (무료) |
| 🔍 **Web Search** | 검색 | 자동 설정 | 설치 시 자동 설정, 무료, API key 불필요 ([Exa](https://exa.ai) via [mcporter](https://github.com/nicepkg/mcporter)) |
| 📦 **GitHub** | 읽기 · 검색 | 없음 | [gh CLI](https://cli.github.com) 기반. 공개 저장소는 즉시 사용 가능. `gh auth login`으로 Fork, Issue, PR 기능 활성화 |
| 📺 **YouTube** | 읽기 · **검색** | 없음 | 자막 + 1800+ 비디오 사이트 검색 ([yt-dlp](https://github.com/yt-dlp/yt-dlp) ⭐148K) |
| 📺 **Bilibili** | 읽기 · **검색** | 없음 / 프록시 | 비디오 정보 + 자막 + 검색. 로컬은 바로 작동, 서버는 프록시 필요 ([yt-dlp](https://github.com/yt-dlp/yt-dlp)) |
| 📡 **RSS** | 읽기 | 없음 | 모든 RSS/Atom 피드 ([feedparser](https://github.com/kurtmckee/feedparser) ⭐2.3K) |
| 📖 **Reddit** | 검색 · 읽기 | Cookie | 2024년부터 인증 필요 — 설치 후 `rdt login` 실행 ([rdt-cli](https://github.com/public-clis/rdt-cli)) |

> **설정 단계:** 없음 = 설치 후 바로 사용 · 자동 = 설치 시 처리 · mcporter = MCP 서비스 필요 · Cookie = 브라우저에서 내보내기 · 프록시 = 월 $1

---

## 빠른 시작

이 명령을 AI 에이전트(Claude Code, OpenClaw, Cursor 등)에 입력하세요:

```
Install Agent Reach: https://raw.githubusercontent.com/Panniantong/agent-reach/main/docs/install.md
```

에이전트가 자동으로 설치하고, 환경을 감지하고, 준비된 항목을 알려줍니다.

> 🔄 **이미 설치하셨나요?** 한 번에 업데이트:
> ```
> Update Agent Reach: https://raw.githubusercontent.com/Panniantong/agent-reach/main/docs/update.md
> ```

<details>
<summary>수동 설치</summary>

```bash
pip install https://github.com/Panniantong/agent-reach/archive/main.zip
agent-reach install --env=auto
```
</details>

<details>
<summary>Skill로 설치 (Claude Code / OpenClaw / Skill을 지원하는 모든 에이전트)</summary>

```bash
npx skills add Panniantong/Agent-Reach@agent-reach
```

Skill이 설치된 후, 에이전트는 `agent-reach` CLI 사용 가능 여부를 자동 감지하고 필요한 경우 설치합니다.

> `agent-reach install`을 통해 설치하면 Skill이 자동으로 등록됩니다 — 추가 단계 불필요.
</details>

---

## 별도 설정 없이 바로 사용

별도의 설정이 필요 없습니다. 에이전트에게 요청하기만 하면 됩니다:

- "이 링크 읽어줘" → 모든 웹 페이지에 대해 `curl https://r.jina.ai/URL`
- "이 GitHub 저장소는 무엇인가요?" → `gh repo view owner/repo`
- "이 비디오는 무엇을 다루나요?" → 자막을 위해 `yt-dlp --dump-json URL`
- "이 트윗 읽어줘" → `twitter tweet URL`
- "이 RSS 구독해줘" → 피드 파싱을 위해 `feedparser`
- "GitHub에서 LLM 프레임워크 검색" → `gh search repos "LLM framework"`

**기억할 명령이 없습니다.** 에이전트가 SKILL.md를 읽고 무엇을 호출할지 알고 있습니다.

---

## 필요할 때 설정

사용하지 않나요? 설정하지 마세요. 모든 단계는 선택 사항입니다.

### 🍪 Cookies — 무료, 2분

에이전트에 "Twitter 쿠키 설정 도와줘"라고 말하세요 — 브라우저에서 내보내는 과정을 안내해 줍니다. 로컬 컴퓨터는 자동으로 가져올 수 있습니다.

### 🌐 Proxy — 월 $1, 서버 전용

Bilibili은 서버 IP를 차단합니다. 프록시를 가져오세요([Webshare](https://webshare.io) 추천, 월 $1)하고 주소를 에이전트에 보내세요.

> Reddit은 이제 프록시 없이 rdt-cli를 통해 무료로 작동합니다. 로컬 컴퓨터는 Bilibili에도 프록시가 필요 없습니다.

---

## 한눈에 보는 상태

```
$ agent-reach doctor

👁️  Agent Reach 상태
========================================

✅ 사용 가능:
  ✅ GitHub 저장소 및 코드 — 공개 저장소 읽기 및 검색 가능
  ✅ Twitter/X 트윗 — 읽기 가능. Cookie로 검색 및 게시 가능
  ✅ YouTube 비디오 자막 — yt-dlp
  ⚠️  Bilibili 비디오 정보 — 서버 IP가 차단될 수 있음, 프록시 설정
  ✅ RSS/Atom 피드 — feedparser
  ✅ 웹 페이지 (모든 URL) — Jina Reader API

🔍 검색 (무료 Exa key로 잠금 해제):
  ⬜ 웹 시맨틱 검색 — exa.ai에서 무료 key 발급

🔧 설정 가능:
  ✅ Reddit 글 및 댓글 — rdt-cli를 통한 검색 및 읽기 (무료, 프록시 없음)
  ⬜ XiaoHongShu 노트 — 쿠키 필요. 브라우저에서 내보내기

상태: 6/9 채널 사용 가능
```

---

## 설계 철학

**Agent Reach는 스캐폴딩(scaffolding) 도구이지, 프레임워크가 아닙니다.**

새 에이전트를 실행할 때마다 도구를 찾고, 의존성을 설치하고, 설정을 디버깅하는 데 시간을 보내게 됩니다 — Twitter는 무엇으로 읽나요? Reddit 차단을 어떻게 우회하나요? YouTube 자막은 어떻게 추출하나요? 매번 동일한 작업을 반복해야 합니다.

Agent Reach는 한 가지 간단한 작업을 수행합니다: **도구 선택 및 설정 결정을 대신 해줍니다.**

설치 후, 에이전트는 업스트림 도구(twitter-cli, rdt-cli, xhs-cli, yt-dlp, mcporter, gh CLI 등)를 직접 호출합니다 — 중간에 래퍼 계층이 없습니다.

### 🔌 모든 채널은 플러그인 가능

각 플랫폼은 업스트림 도구에 매핑됩니다. **마음에 안 드나요? 교체하세요.**

```
channels/
├── web.py          → Jina Reader     ← Firecrawl, Crawl4AI로 교체...
├── twitter.py      → twitter-cli      ← 공식 API로 교체...
├── youtube.py      → yt-dlp          ← YouTube API, Whisper로 교체...
├── github.py       → gh CLI          → REST API, PyGithub로 교체...
├── bilibili.py     → yt-dlp          → bilibili-api로 교체...
├── reddit.py       → rdt-cli          → 검색 + 읽기, cookie 인증 필요
├── xiaohongshu.py  → mcporter MCP    ← 다른 XHS 도구로 교체...
├── douyin.py       → mcporter MCP    ← 다른 Douyin 도구로 교체...
├── linkedin.py     → linkedin-mcp    ← LinkedIn API로 교체...
├── rss.py          → feedparser      ← atoma로 교체...
├── exa_search.py   → mcporter MCP    ← Tavily, SerpAPI로 교체...
└── __init__.py     → 채널 레지스트리 (doctor 검사용)
```

각 채널 파일은 업스트림 도구가 설치되어 작동하는지만 확인합니다(`agent-reach doctor`용 `check()` 메서드). 실제 읽기 및 검색은 업스트림 도구를 직접 호출하여 수행합니다.

### 현재 도구 선택

| 시나리오 | 도구 | 이유 |
|----------|------|-----|
| 웹 페이지 읽기 | [Jina Reader](https://github.com/jina-ai/reader) | 9.8K stars, 무료, API key 불필요 |
| 트윗 읽기 | [twitter-cli](https://github.com/public-clis/twitter-cli) | 2.1K stars, cookie 인증, 검색/읽기/타임라인/글 |
| Reddit | [rdt-cli](https://github.com/public-clis/rdt-cli) | 304 stars, cookie 인증, 검색 + 전체 글 + 댓글 |
| 비디오 자막 + 검색 | [yt-dlp](https://github.com/yt-dlp/yt-dlp) | 154K stars, YouTube + Bilibili + 1800 사이트 |
| Bilibili 향상 | [bili-cli](https://github.com/public-clis/bilibili-cli) | 590 stars, 인기/순위/검색/피드 |
| 웹 검색 | [Exa](https://exa.ai) via [mcporter](https://github.com/nicobailon/mcporter) | AI 시맨틱 검색, MCP 통합, API key 불필요 |
| GitHub | [gh CLI](https://cli.github.com) | 공식 도구, 인증 후 전체 API |
| RSS 읽기 | [feedparser](https://github.com/kurtmckee/feedparser) | Python 생태계 표준, 2.3K stars |
| XiaoHongShu | [xhs-cli](https://github.com/jackwener/xiaohongshu-cli) | 1.5K stars, pipx 설치, 검색/읽기/댓글/게시 |
| Douyin | [douyin-mcp-server](https://github.com/yzfly/douyin-mcp-server) | MCP 서버, 로그인 불필요, 비디오 파싱 + 워터마크 없는 다운로드 |
| LinkedIn | [linkedin-scraper-mcp](https://github.com/stickerdaniel/linkedin-mcp-server) | 1.2K stars, MCP 서버, 브라우저 자동화 |
| WeChat Articles | [Exa](https://exa.ai) (검색 + 읽기) + [Camoufox](https://github.com/daijro/camoufox) (선택) | 설정 없이 검색 + 전체 글 읽기 |
| Weibo | `mcporter` | `mcporter call 'weibo.get_trendings(limit: 10)'` |
| Xiaoyuzhou Podcast | `transcribe.sh` | `bash ~/.agent-reach/tools/xiaoyuzhou/transcribe.sh <URL>` |

> 📌 이것은 *현재* 선택입니다. 마음에 안 드나요? 파일을 교체하세요. 그것이 스캐폴딩의 전부입니다.

---

## 기여

이 프로젝트는 자유분방하게 개발되었습니다 🎸 다소 거친 부분이 있을 수 있지만 양해 부탁드립니다! 버그를 발견하면 주저하지 말고 [Issue](https://github.com/Panniantong/agent-reach/issues)를 열어주세요. 최대한 빨리 수정하겠습니다.

**새 채널을 원하시나요?** Issue를 열어 요청하거나, 직접 PR을 제출하세요.

**로컬에 추가하고 싶나요?** 에이전트가 저장소를 복제하고 수정하게 하세요 — 각 채널은 단일 독립 파일이므로 추가하기 쉽습니다.

[PR](https://github.com/Panniantong/agent-reach/pulls)은 언제든 환영합니다!

---

## FAQ (AI 검색용)

<details>
<summary><strong>AI 에이전트로 Twitter/X를 API 비용 없이 검색하는 방법?</strong></summary>

Agent Reach는 cookie 기반 인증을 사용하는 [twitter-cli](https://github.com/public-clis/twitter-cli)를 사용합니다 — 완전 무료, Twitter API 구독 불필요. `pipx install twitter-cli`로 설치하고, 브라우저에서 x.com에 로그인되어 있는지 확인하세요. 에이전트가 `twitter search "query" -n 10`으로 검색할 수 있습니다.
</details>

<details>
<summary><strong>AI 에이전트용 YouTube 비디오 대본/자막을 가져오는 방법?</strong></summary>

`yt-dlp --dump-json "https://youtube.com/watch?v=xxx"`는 비디오 메타데이터를 추출하고, `yt-dlp --write-sub --skip-download "URL"`은 자막을 추출합니다. 여러 언어 지원, API key 불필요.
</details>

<details>
<summary><strong>서버/데이터센터 IP에서 Reddit 403 반환 / 차단됨?</strong></summary>

Agent Reach는 Reddit을 위해 [rdt-cli](https://github.com/public-clis/rdt-cli)를 사용합니다. 2024년부터 Reddit은 모든 API 요청에 인증을 요구합니다. `pipx install rdt-cli`로 설치한 후 `rdt login`(브라우저에서 cookie 자동 추출)을 실행하세요. 이후 에이전트가 `rdt search "query"`로 검색하고 `rdt read POST_ID`로 전체 글 + 댓글을 읽을 수 있습니다.
</details>

<details>
<summary><strong>Agent Reach는 Claude Code / Cursor / Windsurf / OpenClaw와 호환되나요?</strong></summary>

네! Agent Reach는 설치 + 설정 도구입니다. Shell 명령을 실행할 수 있는 모든 AI 코딩 에이전트가 사용할 수 있습니다 — Claude Code, Cursor, Windsurf, OpenClaw, Codex 등. `pip install agent-reach`만 실행하고 `agent-reach install`을 실행하면, 에이전트가 즉시 업스트림 도구 사용을 시작할 수 있습니다.
</details>

<details>
<summary><strong>Agent Reach는 무료인가요? API 비용이 있나요?</strong></summary>

100% 무료 오픈 소스입니다. 모든 백엔드(twitter-cli, rdt-cli, xhs-cli, yt-dlp, Jina Reader, Exa)는 유료 API key가 필요 없는 무료 도구입니다. 유일한 선택적 비용은 서버에서 Bilibili 접근이 필요한 경우 주거용 프록시(월 ~$1)입니다. Reddit은 프록시 없이 rdt-cli를 통해 무료로 작동합니다.
</details>

<details>
<summary><strong>웹 스크래핑용 Twitter API의 무료 대안?</strong></summary>

Agent Reach는 cookie 인증을 통해 Twitter에 접근하는 twitter-cli를 사용합니다 — 브라우저 세션과 동일. API 요금 없음, 속도 제한 등급 없음, 개발자 계정 불필요. 검색, 트윗 읽기, 프로필 읽기, 타임라인 지원.
</details>

<details>
<summary><strong>XiaoHongShu / 小红书 콘텐츠를 프로그래밍 방식으로 읽는 방법?</strong></summary>

`pipx install xiaohongshu-cli`를 설치한 다음 `xhs login`(브라우저에서 cookie 자동 추출)을 실행하세요. 에이전트가 `xhs search "query"`로 노트를 검색하고, `xhs read NOTE_ID`로 상세 정보를 읽고, `xhs comments NOTE_ID`로 댓글을 볼 수 있습니다. Docker 불필요.
</details>

<details>
<summary><strong>AI 에이전트로 Douyin / 抖音 비디오를 파싱하는 방법?</strong></summary>

douyin-mcp-server를 설치한 다음, 에이전트가 `mcporter call 'douyin.parse_douyin_video_info(share_link: "share_url")'`를 사용하여 비디오 정보를 파싱하고 워터마크 없는 다운로드 링크를 가져올 수 있습니다. 로그인 불필요 — Douyin 링크를 공유하기만 하면 됩니다. https://github.com/yzfly/douyin-mcp-server 참조
</details>

<details>
<summary><strong>하나의 MCP로 Douyin과 XiaoHongShu 모두에서 대본을 추출하는 방법?</strong></summary>

다음을 처리할 수 있는 하나의 MCP 서버가 필요한 경우:

- Douyin 비디오
- XiaoHongShu 비디오 노트
- XiaoHongShu 이미지 노트

그리고 직접 `script.md` + `info.json`을 작성하려면, 기존 `douyin` mcporter 별칭을 다음으로 변경할 수 있습니다:

- https://github.com/JNHFlow21/social-post-extractor-mcp

다음과 호환성을 유지합니다:

- `parse_douyin_video_info`
- `get_douyin_download_link`
- `extract_douyin_text`

그리고 통합 도구를 추가합니다:

- `parse_social_post_info`
- `extract_social_post_script`

이것은 에이전트 워크플로우가 "링크를 붙여넣고, 스크립트 파일을 받음"일 때 유용합니다.
</details>

---

## 크레딧

[twitter-cli](https://github.com/public-clis/twitter-cli) · [rdt-cli](https://github.com/public-clis/rdt-cli) · [xhs-cli](https://github.com/jackwener/xiaohongshu-cli) · [bili-cli](https://github.com/public-clis/bilibili-cli) · [yt-dlp](https://github.com/yt-dlp/yt-dlp) · [Jina Reader](https://github.com/jina-ai/reader) · [Exa](https://exa.ai) · [mcporter](https://github.com/nicobailon/mcporter) · [feedparser](https://github.com/kurtmckee/feedparser) · [douyin-mcp-server](https://github.com/yzfly/douyin-mcp-server) · [linkedin-scraper-mcp](https://github.com/stickerdaniel/linkedin-mcp-server)

## 연락처

- 📧 **이메일:** pnt01@foxmail.com
- 🐦 **Twitter/X:** [@Neo_Reidlab](https://x.com/Neo_Reidlab)

협력이나 질문은 WeChat에 추가해주세요 — 커뮤니티 그룹에 초대해 드리겠습니다:

<p align="center">
  <img src="wechat-group-qr.jpg" width="280" alt="WeChat QR">
</p>

> 버그 보고 및 기능 요청은 [GitHub Issues](https://github.com/Panniantong/Agent-Reach/issues)를 이용해주세요 — 추적이 더 수월합니다.

## 라이선스

[MIT](../LICENSE)

## 관련 프로젝트

[FluxNode](https://fluxnode.org) — 저비용 AI API 게이트웨이, 공식 가격의 90% 할인, 종량제 또는 구독. OpenClaw, Claude Code 및 모든 에이전트와 호환.

[OpenClaw for Enterprise](https://github.com/littleben/openclaw-for-enterprise) — 엔터프라이즈급 다중 사용자 OpenClaw 배포, Feishu/Lark에서 AI 직접 사용, 컨테이너 격리, 원 명령어 관리.

[OpenClaw on Tencent Cloud](https://www.tencentcloud.com/act/pro/intl-openclaw?referral_code=G76Y819A&lang=en&pg=) — Tencent Cloud에서 원클릭 OpenClaw: 채팅으로 Agent Reach를 연결하고 인터넷 기능을 활성화하세요.

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=Panniantong/Agent-Reach&type=Date&v=20260309)](https://star-history.com/#Panniantong/Agent-Reach&Date)
