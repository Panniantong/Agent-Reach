<h1 align="center">👁️ Agent Reach</h1>

<p align="center">
  <strong>Geben Sie Ihrem AI Agent mit einem Klick Zugang zum gesamten Internet</strong>
</p>

<p align="center">
  <a href="../LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue.svg?style=for-the-badge" alt="MIT License"></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.10+-green.svg?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.10+"></a>
  <a href="https://github.com/Panniantong/agent-reach/stargazers"><img src="https://img.shields.io/github/stars/Panniantong/agent-reach?style=for-the-badge" alt="GitHub Stars"></a>
</p>

<p align="center">
  <a href="#schnellstart">Schnellstart</a> · <a href="../README.md">中文</a> · <a href="README_en.md">English</a> · <a href="README_ja.md">日本語</a> · <a href="README_de.md">Deutsch</a> · <a href="#unterstützte-plattformen">Plattformen</a> · <a href="#design-philosophie">Philosophie</a>
</p>

---

## Warum Agent Reach?

AI Agents können bereits auf das Internet zugreifen – aber "können online gehen" ist nur der Anfang.

Die wertvollsten Informationen befinden sich auf sozialen und Nischenplattformen: Twitter-Diskussionen, Reddit-Feedback, YouTube-Tutorials, XiaoHongShu-Bewertungen, Bilibili-Videos, GitHub-Aktivitäten... **Dort ist die Informationsdichte am höchsten**, aber jede Plattform hat ihre eigenen Barrieren:

| Problem | Realität |
|---------|----------|
| Twitter API | Pay-per-use, moderate Nutzung ~$215/Monat |
| Reddit | Server-IPs erhalten 403-Fehler |
| XiaoHongShu | Login zum Durchsuchen erforderlich |
| Bilibili | Blockiert IPs aus dem Ausland / von Servern |

Um Ihren Agenten mit diesen Plattformen zu verbinden, müssten Sie Tools finden, Abhängigkeiten installieren und Konfigurationen debuggen – eins nach dem anderen.

**Agent Reach verwandelt dies in einen einzigen Befehl:**

```
Install Agent Reach: https://raw.githubusercontent.com/Panniantong/agent-reach/main/docs/install.md
```

Kopieren Sie das für Ihren Agenten. Einige Minuten später kann er Tweets lesen, Reddit durchsuchen und Bilibili ansehen.

**Bereits installiert? Update mit einem Befehl:**

```
Update Agent Reach: https://raw.githubusercontent.com/Panniantong/agent-reach/main/docs/update.md
```

### ✅ Bevor Sie beginnen, sollten Sie Folgendes wissen

| | |
|---|---|
| 💰 **Völlig kostenlos** | Alle Tools sind Open Source, alle APIs sind kostenlos. Die einzigen möglichen Kosten sind ein Server-Proxy ($1/Monat) — lokale Computer benötigen keinen |
| 🔒 **Privatsphäre sicher** | Cookies bleiben lokal. Werden niemals hochgeladen. Vollständig Open Source — kann jederzeit auditiert werden |
| 🔄 **Immer aktuell** | Upstream-Tools (yt-dlp, bird, Jina Reader usw.) werden verfolgt und regelmäßig aktualisiert |
| 🤖 **Funktioniert mit jedem Agenten** | Claude Code, OpenClaw, Cursor, Windsurf… jeder Agent, der Befehle ausführen kann |
| 🩺 **Eingebaute Diagnose** | `agent-reach doctor` — ein Befehl zeigt, was funktioniert, was nicht und wie man es behebt |

---

## Unterstützte Plattformen

| Plattform | Fähigkeiten | Setup | Hinweise |
|-----------|-------------|:-----:|-------|
| 🌐 **Web** | Lesen | Ohne Konfig | Beliebige URL → sauberes Markdown ([Jina Reader](https://github.com/jina-ai/reader) ⭐9.8K) |
| 🐦 **Twitter/X** | Lesen · Suchen | Ohne Konfig / Cookie | Einzelne Tweets sind sofort lesbar. Cookie schaltet Suche, Timeline, Posten frei ([bird](https://www.npmjs.com/package/@steipete/bird)) |
| 📕 **XiaoHongShu** | Lesen · Suchen · **Posten · Kommentieren · Liken** | mcporter | Über [xiaohongshu-mcp](https://github.com/user/xiaohongshu-mcp) interne API, installieren und loslegen |
| 🎵 **Douyin** | Video-Parsing · Download ohne Wasserzeichen | mcporter | Über [douyin-mcp-server](https://github.com/yzfly/douyin-mcp-server), kein Login erforderlich |
| 💼 **LinkedIn** | Jina Reader (öffentliche Seiten) | Vollständige Profile, Unternehmen, Jobsuche | Sagen Sie Ihrem Agenten "Hilf mir, LinkedIn einzurichten" |
| 💬 **WeChat Articles** | Suchen + Lesen | Ohne Konfig | WeChat-Artikel (Full Markdown) suchen und lesen ([wechat-article-for-ai](https://github.com/Panniantong/wechat-article-for-ai) + [miku_ai](https://github.com/GobinFan/Miku_Spider)) |
| 📰 **Weibo** | Trends · Suche · Feeds · Kommentare | Ohne Konfig | Heißeste Suchen, Inhalts-/Benutzer-/Themensuche, Feeds, Kommentare ([mcp-server-weibo](https://github.com/Panniantong/mcp-server-weibo)) |
| 💻 **V2EX** | Heiße Themen · Knotenpunkte · Themendetails + Antworten · Benutzerprofil | Ohne Konfig | Öffentliche JSON-API, keine Authentifizierung erforderlich. Ideal für Tech-Community-Inhalte |
| 📈 **Xueqiu (雪球)** | Aktienkurse · Suche · Beliebte Beiträge · Beliebte Aktien | Browser Cookie | Sagen Sie Ihrem Agenten "Hilf mir, Xueqiu einzurichten" |
| 🎙️ **Xiaoyuzhou Podcast** | Transkription | Kostenloser API-Key | Podcast-Audio → vollständiges Text-Transkript via Groq Whisper (kostenlos) |
| 🔍 **Web-Suche** | Suchen | Auto-konfiguriert | Automatische Einrichtung während der Installation, kostenlos, kein API-Key ([Exa](https://exa.ai) über [mcporter](https://github.com/nicepkg/mcporter)) |
| 📦 **GitHub** | Lesen · Suchen | Ohne Konfig | Angetrieben durch [gh CLI](https://cli.github.com). Öffentliche Repositories funktionieren sofort. `gh auth login` schaltet Fork, Issue, PR frei |
| 📺 **YouTube** | Lesen · **Suchen** | Ohne Konfig | Untertitel + Suche in über 1800 Videoportalen ([yt-dlp](https://github.com/yt-dlp/yt-dlp) ⭐148K) |
| 📺 **Bilibili** | Lesen · **Suchen** | Ohne Konfig / Proxy | Video-Infos + Untertitel + Suche. Lokal direkt funktionsfähig, Server benötigen einen Proxy ([yt-dlp](https://github.com/yt-dlp/yt-dlp)) |
| 📡 **RSS** | Lesen | Ohne Konfig | Beliebige RSS/Atom-Feeds ([feedparser](https://github.com/kurtmckee/feedparser) ⭐2.3K) |
| 📖 **Reddit** | Suchen · Lesen | Ohne Konfig | Suchen und Lesen über Exa (kostenlos, kein Proxy erforderlich) |

> **Setup-Stufen:** Ohne Konfig = Installieren und loslegen · Auto-konfiguriert = Wird während der Installation behandelt · mcporter = Benötigt MCP-Server · Cookie = Aus dem Browser exportieren · Proxy = $1/Monat

---

## Schnellstart

Kopieren Sie dies an Ihren AI Agenten (Claude Code, OpenClaw, Cursor usw.):

```
Install Agent Reach: https://raw.githubusercontent.com/Panniantong/agent-reach/main/docs/install.md
```

Der Agent führt die automatische Installation durch, erkennt Ihre Umgebung und teilt Ihnen mit, was einsatzbereit ist.

> 🔄 **Bereits installiert?** Update mit einem Befehl:
> ```
> Update Agent Reach: https://raw.githubusercontent.com/Panniantong/agent-reach/main/docs/update.md
> ```

<details>
<summary>Manuelle Installation</summary>

```bash
pip install https://github.com/Panniantong/agent-reach/archive/main.zip
agent-reach install --env=auto
```
</details>

<details>
<summary>Als Skill installieren (Claude Code / OpenClaw / jeder Agent mit Skills-Unterstützung)</summary>

```bash
npx skills add Panniantong/Agent-Reach@agent-reach
```

Nachdem der Skill installiert wurde, erkennt der Agent automatisch, ob die CLI `agent-reach` verfügbar ist, und installiert sie bei Bedarf.

> Wenn Sie über `agent-reach install` installieren, wird der Skill automatisch registriert – es sind keine weiteren Schritte erforderlich.
</details>

---

## Sofort einsatzbereit

Keine Konfiguration erforderlich – weisen Sie Ihren Agenten einfach an:

- "Lies diesen Link" → `curl https://r.jina.ai/URL` für jede beliebige Webseite
- "Worum geht es in diesem GitHub-Repository?" → `gh repo view owner/repo`
- "Was behandelt dieses Video?" → `yt-dlp --dump-json URL` für Untertitel
- "Lies diesen Tweet" → `bird read URL`
- "Abonniere diesen RSS-Feed" → `feedparser` zum Parsen von Feeds
- "Suche GitHub nach LLM-Frameworks" → `gh search repos "LLM framework"`

**Keine Befehle zum Auswendiglernen.** Der Agent liest die SKILL.md und weiß selbst, was aufzurufen ist.

---

## Nach Bedarf freischalten

Sie verwenden es nicht? Dann müssen Sie es nicht konfigurieren. Jeder Schritt ist optional.

### 🍪 Cookies — Kostenlos, 2 Minuten

Sagen Sie Ihrem Agenten "Hilf mir, Twitter-Cookies zu konfigurieren" – er wird Sie durch den Export aus dem Browser leiten. Lokale Computer können automatisch importieren.

### 🌐 Proxy — $1/Monat, nur für Server

Bilibili blockiert Server-IPs. Holen Sie sich einen Proxy (empfohlen: [Webshare](https://webshare.io), $1/Monat) und senden Sie die Adresse an Ihren Agenten.

> Reddit funktioniert jetzt über Exa kostenlos ohne Proxy. Lokale Computer benötigen ebenfalls keinen Proxy für Bilibili.

---

## Status auf einen Blick

```
$ agent-reach doctor

👁️  Agent Reach Status
========================================

✅ Ready to use:
  ✅ GitHub repos and code — public repos readable and searchable
  ✅ Twitter/X tweets — readable. Cookie unlocks search and posting
  ✅ YouTube video subtitles — yt-dlp
  ⚠️  Bilibili video info — server IPs may be blocked, configure proxy
  ✅ RSS/Atom feeds — feedparser
  ✅ Web pages (any URL) — Jina Reader API

🔍 Search (free Exa key to unlock):
  ⬜ Web semantic search — sign up at exa.ai for free key

🔧 Configurable:
  ✅ Reddit posts and comments — search and read via Exa (free, no proxy)
  ⬜ XiaoHongShu notes — needs cookie. Export from browser

Status: 6/9 channels available
```

---

## Design-Philosophie

**Agent Reach ist ein Gerüst (Scaffolding-Tool), kein Framework.**

Jedes Mal, wenn Sie einen neuen Agenten einrichten, verbringen Sie Zeit damit, Tools zu finden, Abhängigkeiten zu installieren und Konfigurationen zu debuggen – was liest Twitter? Wie umgehen Sie Reddit-Blockaden? Wie extrahieren Sie YouTube-Untertitel? Jedes Mal wiederholen Sie die gleiche Arbeit.

Agent Reach macht eine einfache Sache: **Es nimmt Ihnen diese Entscheidungen zur Tool-Auswahl und Konfiguration ab.**

Nach der Installation ruft Ihr Agent die Upstream-Tools direkt auf (bird CLI, yt-dlp, mcporter, gh CLI usw.) – keine Wrapper-Schicht dazwischen.

### 🔌 Jeder Kanal ist austauschbar

Jede Plattform ist einem Upstream-Tool zugeordnet. **Ihnen gefällt eines nicht? Tauschen Sie es einfach aus.**

```
channels/
├── web.py          → Jina Reader     ← zu Firecrawl, Crawl4AI wechseln…
├── twitter.py      → bird CLI         ← zu Nitter, offizieller API wechseln…
├── youtube.py      → yt-dlp          ← zu YouTube API, Whisper wechseln…
├── github.py       → gh CLI          ← zu REST API, PyGithub wechseln…
├── bilibili.py     → yt-dlp          ← zu bilibili-api wechseln…
├── reddit.py       → Exa             ← Suchen + Lesen, kein Proxy erforderlich
├── xiaohongshu.py  → mcporter MCP    ← zu anderen XHS-Tools wechseln…
├── douyin.py       → mcporter MCP    ← zu anderen Douyin-Tools wechseln…
├── linkedin.py     → linkedin-mcp    ← zu LinkedIn API wechseln…
├── rss.py          → feedparser      ← zu atoma wechseln…
├── exa_search.py   → mcporter MCP    ← zu Tavily, SerpAPI wechseln…
└── __init__.py     → Channel-Registrierung (für Doctor-Checks)
```

Jede Kanal-Datei überprüft nur, ob das jeweilige Upstream-Tool installiert und funktionsfähig ist (Methode `check()` für `agent-reach doctor`). Das eigentliche Lesen und Suchen wird direkt durch den Aufruf der Upstream-Tools erledigt.

### Aktuelle Tool-Auswahl

| Szenario | Tool | Warum |
|----------|------|-------|
| Webseiten lesen | [Jina Reader](https://github.com/jina-ai/reader) | 9,8K Sterne, kostenlos, kein API-Key erforderlich |
| Tweets lesen | [bird](https://www.npmjs.com/package/@steipete/bird) | Cookie-Auth, kostenlos. Offizielle API ist Pay-per-use ($0,005/gelesenem Beitrag) |
| Video-Untertitel + Suche | [yt-dlp](https://github.com/yt-dlp/yt-dlp) | 148K Sterne, YouTube + Bilibili + 1800 Seiten |
| Web-Suche | [Exa](https://exa.ai) über [mcporter](https://github.com/nicepkg/mcporter) | KI semantische Suche, MCP-Integration, kein API-Key |
| GitHub | [gh CLI](https://cli.github.com) | Offizielles Tool, vollständige API nach Auth |
| RSS lesen | [feedparser](https://github.com/kurtmckee/feedparser) | Standard im Python-Ökosystem, 2,3K Sterne |
| XiaoHongShu | [xiaohongshu-mcp](https://github.com/user/xiaohongshu-mcp) | Interne API, umgeht Anti-Bot |
| Douyin | [douyin-mcp-server](https://github.com/yzfly/douyin-mcp-server) | MCP-Server, kein Login erforderlich, Video-Parsing + wasserzeichenfreier Download |
| LinkedIn | [linkedin-scraper-mcp](https://github.com/stickerdaniel/linkedin-mcp-server) | 900+ Sterne, MCP-Server, Browser-Automatisierung |
| WeChat Articles | [wechat-article-for-ai](https://github.com/Panniantong/wechat-article-for-ai) + [miku_ai](https://github.com/GobinFan/Miku_Spider) | Stealth-Browser zum Lesen vollständiger Artikel + Sogou-Suche |
| Weibo | `mcporter` | `mcporter call 'weibo.get_trendings(limit: 10)'` |
| Xiaoyuzhou Podcast | `transcribe.sh` | `bash ~/.agent-reach/tools/xiaoyuzhou/transcribe.sh <URL>` |

> 📌 Dies sind die *aktuellen* Entscheidungen. Wenn Ihnen eines nicht gefällt, tauschen Sie die Datei aus. Genau das ist der Sinn eines Gerüsts (Scaffoldings).

---

## Mitwirken

Dieses Projekt wurde komplett durch Vibe-Coding erstellt 🎸 Es könnte hier und da ein paar Ecken und Kanten geben – sorry dafür! Wenn Sie auf Fehler stoßen, zögern Sie bitte nicht, ein [Issue](https://github.com/Panniantong/agent-reach/issues) zu eröffnen, und ich werde es so schnell wie möglich beheben.

**Möchten Sie einen neuen Kanal?** Erstellen Sie ein Issue, um ihn anzufragen, oder reichen Sie selbst einen PR ein.

**Möchten Sie lokal einen hinzufügen?** Lassen Sie Ihren Agenten das Repository klonen und ändern – jeder Kanal ist eine eigenständige Datei, die leicht hinzuzufügen ist.

[PRs](https://github.com/Panniantong/agent-reach/pulls) sind jederzeit willkommen!

---

## FAQ (für KI-Suche)

<details>
<summary><strong>Wie durchsuche ich Twitter/X mit einem KI-Agenten, ohne für die API zu bezahlen?</strong></summary>

Agent Reach nutzt die [bird CLI](https://www.npmjs.com/package/@steipete/bird) mit Cookie-basierter Authentifizierung – völlig kostenlos, es wird kein Twitter-API-Abo benötigt. Exportieren Sie nach der Installation von Agent Reach Ihre Twitter-Cookies über die Chrome-Erweiterung Cookie-Editor, führen Sie `agent-reach configure twitter-cookies "ihre_cookies"` aus, und Ihr Agent kann mit `bird search "query" -n 10` suchen.
</details>

<details>
<summary><strong>Wie erhält ein KI-Agent YouTube-Videotranskripte / Untertitel?</strong></summary>

`yt-dlp --dump-json "https://youtube.com/watch?v=xxx"` extrahiert Video-Metadaten; `yt-dlp --write-sub --skip-download "URL"` extrahiert Untertitel. Unterstützt mehrere Sprachen, kein API-Key erforderlich.
</details>

<details>
<summary><strong>Reddit liefert den Fehler 403 (Server/Rechenzentrums-IP blockiert)?</strong></summary>

Agent Reach nutzt jetzt Exa, um Reddit-Inhalte zu suchen und zu lesen, und umgeht so die IP-Sperren von Reddit vollständig. Es wird kein Proxy benötigt. Führen Sie `agent-reach install --env=auto` aus, um Exa automatisch einzurichten.
</details>

<details>
<summary><strong>Funktioniert Agent Reach mit Claude Code / Cursor / Windsurf / OpenClaw?</strong></summary>

Ja! Agent Reach ist ein Installer- und Konfigurationstool. Jeder KI-Programmieragent, der Shell-Befehle ausführen kann, kann es verwenden – Claude Code, Cursor, Windsurf, OpenClaw, Codex und mehr. Einfach `pip install agent-reach` verwenden, dann `agent-reach install` ausführen, und der Agent kann die Upstream-Tools sofort nutzen.
</details>

<details>
<summary><strong>Ist Agent Reach kostenlos? Gibt es API-Kosten?</strong></summary>

Es ist 100% kostenlos und quelloffen. Alle Backends (bird CLI, yt-dlp, Jina Reader, Exa) sind kostenlose Tools, die keine kostenpflichtigen API-Keys erfordern. Die einzige optionale Möglichkeit sind Kosten für einen Residential-Proxy (ca. $1/Monat), falls Sie Bilibili-Zugang von einem Server aus benötigen. Reddit funktioniert kostenlos über Exa ohne Proxy.
</details>

<details>
<summary><strong>Kostenlose Alternative zur Twitter-API fürs Web-Scraping?</strong></summary>

Agent Reach nutzt die bird CLI, die über Cookie-Auth – genau wie Ihre Browser-Sitzung – auf Twitter zugreift. Keine API-Gebühren, keine Limitierungsstufen, kein Entwicklerkonto erforderlich. Unterstützt Suchen, das Lesen von Tweets, Profilen und Timelines.
</details>

<details>
<summary><strong>Wie liest man XiaoHongShu / 小红书 Inhalte programmgesteuert?</strong></summary>

Agent Reach integriert sich mit xiaohongshu-mcp (läuft in Docker). Nutzen Sie nach der Einrichtung `mcporter call 'xiaohongshu.get_feed_detail(...)'`, um Notizen zu lesen, oder `mcporter call 'xiaohongshu.search_feeds(keyword: "query")'`, um zu suchen.
</details>

<details>
<summary><strong>Wie parst man Douyin / 抖音 Videos mit einem KI-Agenten?</strong></summary>

Installieren Sie douyin-mcp-server, dann kann Ihr Agent `mcporter call 'douyin.parse_douyin_video_info(share_link: "share_url")'` nutzen, um Video-Infos zu parsen und Download-Links ohne Wasserzeichen abzurufen. Kein Login erforderlich – teilen Sie einfach den Douyin-Link. Siehe https://github.com/yzfly/douyin-mcp-server
</details>

<details>
<summary><strong>Wie extrahiert man Skripte von sowohl Douyin als auch XiaoHongShu mit einem MCP?</strong></summary>

Wenn Sie einen MCP-Server wollen, der Folgendes bewältigt:

- Douyin-Videos
- XiaoHongShu Video-Notizen
- XiaoHongShu Bild-Notizen

und direkt `script.md` + `info.json` schreiben soll, können Sie den bestehenden `douyin` mcporter alias hierauf verweisen:

- https://github.com/JNHFlow21/social-post-extractor-mcp

Er behält die Abwärtskompatibilität bei für:

- `parse_douyin_video_info`
- `get_douyin_download_link`
- `extract_douyin_text`

und fügt vereinheitlichte Tools hinzu:

- `parse_social_post_info`
- `extract_social_post_script`

Das ist nützlich, wenn Ihr Agent-Workflow so aussieht: „Füge einen Link ein, erhalte eine Skript-Datei“.
</details>

---

## Danksagung

[Jina Reader](https://github.com/jina-ai/reader) · [yt-dlp](https://github.com/yt-dlp/yt-dlp) · [bird](https://www.npmjs.com/package/@steipete/bird) · [Exa](https://exa.ai) · [feedparser](https://github.com/kurtmckee/feedparser) · [douyin-mcp-server](https://github.com/yzfly/douyin-mcp-server) · [linkedin-scraper-mcp](https://github.com/stickerdaniel/linkedin-mcp-server)

## Kontakt

- 📧 **E-Mail:** pnt01@foxmail.com
- 🐦 **Twitter/X:** [@Neo_Reidlab](https://x.com/Neo_Reidlab)

Für Kooperationen oder Fragen können Sie mich auf WeChat hinzufügen – ich lade Sie in die Community-Gruppe ein:

<p align="center">
  <img src="wechat-group-qr.jpg" width="280" alt="WeChat QR">
</p>

> Für Fehlerberichte und Funktionsanfragen nutzen Sie bitte [GitHub Issues](https://github.com/Panniantong/Agent-Reach/issues) – das lässt sich leichter nachverfolgen.

## Lizenz

[MIT](../LICENSE)

## Freunde

[FluxNode](https://fluxnode.org) — Preiswertes API-Gateway für KI, 90% günstiger als offizielle Preise, Pay-as-you-go oder Abo. Funktioniert mit OpenClaw, Claude Code und jedem anderen Agenten.

[OpenClaw für Unternehmen](https://github.com/littleben/openclaw-for-enterprise) — Enterprise-fähiges OpenClaw-Deployment für mehrere Benutzer, nutzen Sie KI direkt in Feishu/Lark, Container-Isolation, One-Command-Management.

[OpenClaw auf Tencent Cloud](https://www.tencentcloud.com/act/pro/intl-openclaw?referral_code=G76Y819A&lang=en&pg=) — One-Click OpenClaw auf der Tencent Cloud: Chatten, um Agent Reach zu verbinden und die Leistung des Internets freizuschalten.

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=Panniantong/Agent-Reach&type=Date&v=20260309)](https://star-history.com/#Panniantong/Agent-Reach&Date)
