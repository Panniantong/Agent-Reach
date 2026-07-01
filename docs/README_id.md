<h1 align="center">👁️ Agent Reach</h1>

<p align="center">
  <strong>Berikan AI Agent akses sekali klik ke seluruh internet</strong>
</p>

<p align="center">
  Jalur akses paling andal untuk tiap platform — dipilih, diinstal, dan dicek kesehatannya untuk Anda. Backend bisa datang dan pergi; Anda tidak perlu merasakannya.
</p>

<p align="center">
  <a href="../LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue.svg?style=for-the-badge" alt="MIT License"></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.10+-green.svg?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.10+"></a>
  <a href="https://github.com/Panniantong/agent-reach/stargazers"><img src="https://img.shields.io/github/stars/Panniantong/agent-reach?style=for-the-badge" alt="GitHub Stars"></a>
  <a href="https://trendshift.io/repositories/24387"><img src="https://trendshift.io/api/badge/repositories/24387" alt="Trendshift GitHub Trending #1 Repository of the Day"></a>
</p>

<p align="center">
  <a href="#mulai-cepat">Mulai Cepat</a> · Bahasa Indonesia · <a href="../README.md">中文</a> · <a href="README_en.md">English</a> · <a href="README_ja.md">日本語</a> · <a href="README_ko.md">한국어</a> · <a href="#platform-yang-didukung">Platform</a> · <a href="#filosofi-desain">Filosofi</a>
</p>

> **Tidak berafiliasi dengan token atau kripto:** Agent Reach tidak memiliki token resmi, koin, produk investasi, program klaim fee, koneksi wallet, atau proyek Solana/Pump.fun. Proyek kripto apa pun yang memakai nama Agent Reach, URL GitHub, atau identitas author tidak berafiliasi dengan repository ini. Jangan hubungkan wallet atau klaim fee dari pesan, posting, atau tautan yang mengatasnamakan Agent Reach.

---

## Mengapa Agent Reach?

AI Agent sudah bisa mengakses internet — tetapi "bisa online" baru permulaan.

Informasi paling bernilai tersebar di platform sosial dan niche: diskusi Twitter, feedback Reddit, tutorial YouTube, ulasan XiaoHongShu, video Bilibili, aktivitas GitHub… **Di sanalah kepadatan informasi paling tinggi**, tetapi tiap platform punya penghalangnya sendiri:

| Masalah | Kenyataan |
|---------|-----------|
| Twitter API | Berbayar per penggunaan, pemakaian sedang bisa ~$215/bulan |
| Reddit | IP server sering terkena 403 |
| XiaoHongShu | Perlu login untuk browsing |
| Bilibili | Memblokir IP luar negeri/server |

Untuk menghubungkan Agent Anda ke platform-platform ini, Anda harus mencari tool, memasang dependency, dan debug konfigurasi — satu per satu.

**Agent Reach mengubah semuanya menjadi satu perintah:**

```
Install Agent Reach: https://raw.githubusercontent.com/Panniantong/agent-reach/main/docs/install.md
```

Salin itu ke Agent Anda. Beberapa menit kemudian, Agent bisa membaca tweet, mencari di Reddit, dan menonton Bilibili.

**Sudah terpasang? Update dengan satu perintah:**

```
Update Agent Reach: https://raw.githubusercontent.com/Panniantong/agent-reach/main/docs/update.md
```

### ✅ Hal yang perlu diketahui sebelum mulai

| | |
|---|---|
| 💰 **Sepenuhnya gratis** | Semua tool open source, semua API gratis. Satu-satunya biaya yang mungkin adalah proxy server ($1/bulan) — komputer lokal tidak memerlukannya |
| 🔒 **Aman untuk privasi** | Cookie tetap lokal. Tidak pernah diunggah. Sepenuhnya open source — bisa diaudit kapan saja |
| 🔄 **Selalu diperbarui** | Setiap platform punya daftar backend utama + fallback. Saat satu jalur mati, kami pindah ke jalur berikutnya — Anda tidak perlu merasakan perubahan itu (Juni 2026: Bilibili memblokir yt-dlp dengan 412 → pindah ke bili-cli, tanpa aksi dari Anda) |
| 🤖 **Bekerja dengan Agent apa pun** | Claude Code, OpenClaw, Cursor, Windsurf… semua Agent yang bisa menjalankan perintah |
| 🩺 **Diagnostik bawaan** | `agent-reach doctor` — satu perintah untuk melihat apa yang berjalan, apa yang tidak, dan cara memperbaikinya |

---

## Platform yang Didukung

| Platform | Kemampuan | Setup | Catatan |
|----------|-----------|:-----:|---------|
| 🌐 **Web** | Baca | Tanpa konfigurasi | URL apa pun → Markdown bersih ([Jina Reader](https://github.com/jina-ai/reader) ⭐9.8K) |
| 🐦 **Twitter/X** | Baca · Cari | Cookie | Cookie membuka search, timeline, pembacaan tweet, artikel ([twitter-cli](https://github.com/public-clis/twitter-cli)) |
| 📕 **XiaoHongShu** | Baca · Cari · Komentar | OpenCLI / MCP | Desktop: [OpenCLI](https://github.com/jackwener/opencli) (memakai ulang sesi browser); Server: [xiaohongshu-mcp](https://github.com/xpzouying/xiaohongshu-mcp) (QR login); xhs-cli lama tetap bisa digunakan |
| 💼 **LinkedIn** | Jina Reader (halaman publik) | Profil lengkap, perusahaan, pencarian kerja | Katakan ke Agent: "help me set up LinkedIn" |
| 💻 **V2EX** | Topik populer · Topik node · Detail topik + balasan · Profil user | Tanpa konfigurasi | Public JSON API, tidak butuh auth. Cocok untuk konten komunitas teknologi |
| 📈 **Xueqiu (雪球)** | Quote saham · Search · Hot posts · Hot stocks | Cookie browser | Katakan ke Agent: "help me set up Xueqiu" |
| 🎙️ **Podcast Xiaoyuzhou** | Transkripsi | API key gratis | Audio podcast → transkrip teks penuh via Groq Whisper (gratis) |
| 🔍 **Web Search** | Cari | Auto-configured | Dikonfigurasi otomatis saat install, gratis, tanpa API key ([Exa](https://exa.ai) via [mcporter](https://github.com/nicepkg/mcporter)) |
| 📦 **GitHub** | Baca · Cari | Tanpa konfigurasi | Didukung [gh CLI](https://cli.github.com). Repo publik langsung bisa dibaca. `gh auth login` membuka Fork, Issue, PR |
| 📺 **YouTube** | Baca · **Cari** | Tanpa konfigurasi | Subtitle + search lintas 1800+ situs video ([yt-dlp](https://github.com/yt-dlp/yt-dlp) ⭐148K) |
| 📺 **Bilibili** | Baca · **Cari** | Tanpa konfigurasi | Search + detail video via [bili-cli](https://github.com/public-clis/bilibili-cli) (tanpa login); subtitle via [OpenCLI](https://github.com/jackwener/opencli). yt-dlp terkena 412 dari Bilibili dan tidak lagi dipakai di sini |
| 📡 **RSS** | Baca | Tanpa konfigurasi | Feed RSS/Atom apa pun ([feedparser](https://github.com/kurtmckee/feedparser) ⭐2.3K) |
| 📖 **Reddit** | Cari · Baca | OpenCLI / Cookie | Tidak ada jalur tanpa konfigurasi (anonymous endpoint diblokir). Desktop: [OpenCLI](https://github.com/jackwener/opencli) via sesi browser; atau [rdt-cli](https://github.com/public-clis/rdt-cli) + cookie |

> **Level setup:** Tanpa konfigurasi = install lalu pakai · Auto-configured = ditangani saat install · mcporter = perlu MCP service · Cookie = ekspor dari browser · Proxy = $1/bulan

---

## Mulai Cepat

> ⚠️ **Pengguna OpenClaw: aktifkan permission `exec` terlebih dahulu**
>
> Agent Reach bergantung pada Agent yang bisa menjalankan shell command (`pip install`, `mcporter`, `twitter`, dll.). Jika OpenClaw Anda memakai profil tool default `messaging`, Agent tidak bisa menjalankannya. **Aktifkan `exec` sebelum install:**
>
> ```bash
> openclaw config set tools.profile "coding"
> ```
> Atau set `"tools": { "profile": "coding" }` di `~/.openclaw/openclaw.json`. Setelah mengubahnya, restart Gateway (`openclaw gateway restart`) dan mulai percakapan baru. Platform lain (Claude Code, Cursor, Windsurf, dll.) tidak terdampak.

Salin ini ke AI Agent Anda (Claude Code, OpenClaw, Cursor, dll.):

```
Install Agent Reach: https://raw.githubusercontent.com/Panniantong/agent-reach/main/docs/install.md
```

Agent akan memasang otomatis, mendeteksi environment Anda, dan memberi tahu apa saja yang siap dipakai.

> 🔄 **Sudah terpasang?** Update dengan satu perintah:
> ```
> Update Agent Reach: https://raw.githubusercontent.com/Panniantong/agent-reach/main/docs/update.md
> ```

> 🛡️ **Khawatir soal keamanan?** Pakai safe mode — mode ini tidak otomatis memasang paket sistem, hanya memberi tahu apa yang perlu dilakukan:
> ```
> Install Agent Reach (safe mode): https://raw.githubusercontent.com/Panniantong/agent-reach/main/docs/install.md
> Use the --safe flag during install
> ```

<details>
<summary>Install manual</summary>

```bash
pip install https://github.com/Panniantong/agent-reach/archive/main.zip
agent-reach install --env=auto
```
</details>

<details>
<summary>Install sebagai Skill (Claude Code / OpenClaw / agent apa pun dengan dukungan Skills)</summary>

```bash
npx skills add Panniantong/Agent-Reach@agent-reach
```

Setelah Skill terpasang, Agent akan otomatis mendeteksi apakah CLI `agent-reach` tersedia dan memasangnya jika perlu.

> Jika Anda install via `agent-reach install`, skill otomatis diregistrasikan — tidak perlu langkah tambahan.
>
> Ingin file skill khusus bahasa Inggris? Set locale bahasa Inggris atau export `AGENT_REACH_LANG=en`
> sebelum menjalankan `agent-reach install --env=auto` atau `agent-reach skill --install`.
> File yang terpasang selalu ditulis sebagai `SKILL.md`, jadi mengganti bahasa berarti menjalankan ulang perintah install dengan locale baru dan mengganti file skill sebelumnya.
</details>

---

## Langsung Bisa Dipakai

Tanpa konfigurasi — cukup beri tahu Agent:

- "Read this link" → `curl https://r.jina.ai/URL` untuk halaman web apa pun
- "What's this GitHub repo about?" → `gh repo view owner/repo`
- "What does this video cover?" → `yt-dlp --dump-json URL` untuk subtitle
- "Read this tweet" → `twitter tweet URL`
- "Subscribe to this RSS" → `feedparser` untuk parse feed
- "Search GitHub for LLM frameworks" → `gh search repos "LLM framework"`

**Tidak perlu menghafal command.** Agent membaca SKILL.md dan tahu apa yang perlu dipanggil.

---

## Batas Kapabilitas: Membaca Konten vs Mengoperasikan Halaman Web

Beberapa tugas melampaui sekadar "membaca": mengoperasikan halaman web yang sudah login, mengisi form, mengisolasi banyak akun, menjalankan sesi browser paralel, atau menangani langkah otomatisasi yang rawan hambatan seperti login, verifikasi, dan risk-control prompt. Untuk aksi browser yang "hands-on" seperti ini, Agent Reach bisa dipasangkan dengan tool otomatisasi browser seperti [BrowserAct](https://www.browseract.ai/Agent) — 30+ skill platform siap pakai, mendukung Agent utama seperti Claude Code, OpenClaw, dan Cursor.

---

## Buka Sesuai Kebutuhan

Tidak dipakai? Tidak perlu dikonfigurasi. Semua langkah opsional.

### 🍪 Cookies — Gratis, 2 menit

Katakan ke Agent "help me configure Twitter cookies" — Agent akan memandu Anda mengekspor cookie dari browser. Komputer lokal bisa auto-import.

### 🌐 Proxy — $1/bulan, hanya untuk jaringan terbatas

Sebagian besar pengguna tidak perlu proxy. Jika jaringan Anda memblokir Reddit/Twitter (misalnya mainland China), gunakan proxy ([Webshare](https://webshare.io) direkomendasikan, $1/bulan) dan kirim alamatnya ke Agent — Agent akan menyimpannya dan mengekspor HTTP(S)_PROXY saat memanggil tool.

> Reddit tetap membutuhkan sesi login — OpenCLI memakai sesi browser Anda, atau rdt-cli setelah `rdt login`. Bilibili berjalan via bili-cli tanpa proxy.

---

## Status Sekilas

```
$ agent-reach doctor

👁️  Agent Reach Status
========================================

✅ Ready to use:
  ✅ GitHub repos and code — public repos readable and searchable
  ✅ Twitter/X tweets — readable. Cookie unlocks search and posting
  ✅ YouTube video subtitles — yt-dlp
  ✅ Bilibili search & video detail — bili-cli (subtitles via OpenCLI)
  ✅ RSS/Atom feeds — feedparser
  ✅ Web pages (any URL) — Jina Reader API

🔍 Search (free Exa key to unlock):
  ⬜ Web semantic search — sign up at exa.ai for free key

🔧 Configurable:
  ⬜ Reddit posts and comments — needs login: rdt-cli after `rdt login`, or OpenCLI browser session
  ⬜ XiaoHongShu notes — desktop: OpenCLI (browser session); server: xiaohongshu-mcp (QR)

Status: 6/9 channels available
```

---

## Filosofi Desain

**Agent Reach adalah capability layer, bukan tool baru yang membungkus semuanya.**

Agent Reach berada satu level di atas implementasi spesifik — ia menangani **pemilihan, instalasi, health check, dan routing**, bukan proses membaca itu sendiri. Pembacaan dilakukan oleh Agent Anda dengan memanggil upstream tools secara langsung; tidak ada wrapper layer tambahan.

Setiap kali Anda menyiapkan Agent baru, Anda menghabiskan waktu mencari tool, memasang dependency, dan debug konfigurasi — apa yang bisa membaca Twitter? Bagaimana login ke Reddit? Apa pengganti CLI XiaoHongShu yang sudah tidak maintained? Setiap kali, Anda mengulang pekerjaan yang sama. Agent Reach melakukan satu hal sederhana: **memilih, memasang, dan mengecek jalur akses paling andal untuk tiap platform. Jalur akses bisa berubah (Maret 2026 beberapa single-platform CLI tidak lagi maintained — kami reroute), jadi Anda tidak perlu peduli.**

### 🔌 Setiap platform = daftar backend berurutan (utama + fallback)

Mengganti jalur akses berarti mengubah urutan daftar, bukan menulis ulang kode. `agent-reach doctor` memberi tahu **backend mana yang sedang dipakai oleh setiap platform**.

```
channels/
├── web.py          → Jina Reader
├── twitter.py      → twitter-cli ▸ OpenCLI ▸ bird
├── youtube.py      → yt-dlp
├── github.py       → gh CLI
├── bilibili.py     → bili-cli ▸ OpenCLI ▸ search API (yt-dlp retired, 412-blocked)
├── reddit.py       → OpenCLI ▸ rdt-cli (tidak ada zero-config path, perlu login)
├── xiaohongshu.py  → OpenCLI ▸ xiaohongshu-mcp ▸ xhs-cli
├── linkedin.py     → linkedin-mcp ▸ Jina Reader
├── rss.py          → feedparser
├── exa_search.py   → Exa via mcporter
└── __init__.py     → Channel registry (untuk doctor checks)
```

Setiap file channel **benar-benar mem-probe** backend kandidat secara berurutan (bukan hanya mengecek command ada atau tidak) — backend pertama yang benar-benar bekerja menjadi active backend, dan backend yang rusak disertai resep perbaikannya. Pembacaan dan pencarian sebenarnya dilakukan oleh Agent dengan memanggil upstream tools langsung.

### Pilihan Tool Saat Ini

| Skenario | Utama | Fallback | Alasan |
|----------|-------|----------|--------|
| Membaca halaman web | [Jina Reader](https://github.com/jina-ai/reader) | — | Gratis, tidak perlu API key |
| Membaca tweet | [twitter-cli](https://github.com/public-clis/twitter-cli) | [OpenCLI](https://github.com/jackwener/opencli) | Search andal di uji nyata; OpenCLI fallback memakai sesi browser Anda |
| Reddit | [OpenCLI](https://github.com/jackwener/opencli) (desktop) | [rdt-cli](https://github.com/public-clis/rdt-cli) | Anonymous endpoint diblokir, official API gated — sesi login adalah satu-satunya jalur yang tersisa |
| Subtitle + search YouTube | [yt-dlp](https://github.com/yt-dlp/yt-dlp) | — | 154K stars, masih terbaik untuk YouTube (tidak lagi dipakai untuk Bilibili) |
| Bilibili | [bili-cli](https://github.com/public-clis/bilibili-cli) | OpenCLI ▸ search API | yt-dlp diblokir 412 oleh Bilibili (terverifikasi Juni 2026); bili-cli bisa search dan read tanpa login |
| Search web | [Exa](https://exa.ai) via [mcporter](https://github.com/nicobailon/mcporter) | — | AI semantic search, integrasi MCP, tanpa API key |
| GitHub | [gh CLI](https://cli.github.com) | — | Tool resmi, full API setelah auth |
| Membaca RSS | [feedparser](https://github.com/kurtmckee/feedparser) | — | Standar ekosistem Python |
| XiaoHongShu | [OpenCLI](https://github.com/jackwener/opencli) (desktop) | [xiaohongshu-mcp](https://github.com/xpzouying/xiaohongshu-mcp) (server) ▸ xhs-cli | Author xhs-cli pindah ke OpenCLI (24K stars); sesi browser membuatnya minim friction |
| LinkedIn | [linkedin-scraper-mcp](https://github.com/stickerdaniel/linkedin-mcp-server) | Jina Reader | MCP server, browser automation |
| Podcast Xiaoyuzhou | `transcribe.sh` | — | `bash ~/.agent-reach/tools/xiaoyuzhou/transcribe.sh <URL>` |

> 📌 Ini adalah pilihan *saat ini*, diverifikasi ulang secara rutin di mesin nyata. Saat satu jalur mati, kami pindah ke jalur berikutnya — `agent-reach doctor` selalu memberi tahu mana yang aktif.

---

## Berkontribusi

Proyek ini sepenuhnya vibe-coded 🎸 Mungkin masih ada rough edge di beberapa tempat — mohon maaf! Jika menemukan bug, jangan ragu membuka [Issue](https://github.com/Panniantong/agent-reach/issues), dan akan diperbaiki secepatnya.

**Ingin channel baru?** Buka Issue untuk request, atau kirim PR sendiri.

**Ingin menambahkannya secara lokal?** Minta Agent Anda clone repo ini dan modifikasi — setiap channel adalah satu file mandiri, mudah ditambahkan.

[PR](https://github.com/Panniantong/agent-reach/pulls) selalu diterima!

---

## FAQ (untuk AI search)

<details>
<summary><strong>Bagaimana cara mencari Twitter/X dengan AI agent tanpa membayar API?</strong></summary>

Agent Reach memakai [twitter-cli](https://github.com/public-clis/twitter-cli) dengan autentikasi cookie — sepenuhnya gratis, tidak perlu langganan Twitter API. Install dengan `pipx install twitter-cli`, pastikan Anda sudah login ke x.com di browser, lalu Agent bisa mencari dengan `twitter search "query" -n 10`.
</details>

<details>
<summary><strong>Bagaimana mengambil transkrip/subtitle video YouTube untuk AI agent?</strong></summary>

`yt-dlp --dump-json "https://youtube.com/watch?v=xxx"` mengekstrak metadata video; `yt-dlp --write-sub --skip-download "URL"` mengekstrak subtitle. Mendukung banyak bahasa, tanpa API key.
</details>

<details>
<summary><strong>Reddit mengembalikan 403 dari server / IP datacenter diblokir?</strong></summary>

Reddit memerlukan sesi login untuk semuanya (anonymous endpoint diblokir, dan registrasi official API perlu approval sejak 2025-11). Di desktop, jalur yang disarankan adalah OpenCLI yang memakai sesi reddit.com di browser Anda. Alternatifnya, install rdt-cli dari pinned git source (`pipx install 'git+https://github.com/public-clis/rdt-cli.git'` — PyPI tertinggal), lalu `rdt login`. Agent Anda kemudian bisa search dengan `rdt search "query"` dan membaca post lengkap + komentar dengan `rdt read POST_ID`.
</details>

<details>
<summary><strong>Apakah Agent Reach bekerja dengan Claude Code / Cursor / Windsurf / OpenClaw?</strong></summary>

Ya! Agent Reach adalah tool instalasi + konfigurasi. AI coding agent apa pun yang bisa menjalankan shell command bisa memakainya — Claude Code, Cursor, Windsurf, OpenClaw, Codex, dan lainnya. Cukup `pip install agent-reach`, jalankan `agent-reach install`, dan Agent bisa langsung memakai upstream tools.
</details>

<details>
<summary><strong>Apakah Agent Reach gratis? Ada biaya API?</strong></summary>

100% gratis dan open source. Semua backend (twitter-cli, rdt-cli, xhs-cli, yt-dlp, Jina Reader, Exa) adalah tool gratis yang tidak memerlukan API key berbayar. Satu-satunya biaya opsional adalah residential proxy (~$1/bulan) untuk beberapa skenario server. Reddit tidak berbayar, tetapi perlu sesi login (rdt-cli setelah `rdt login`, atau OpenCLI memakai ulang sesi browser Anda).
</details>

<details>
<summary><strong>Alternatif gratis Twitter API untuk web scraping?</strong></summary>

Agent Reach memakai twitter-cli yang mengakses Twitter lewat cookie auth — sama seperti sesi browser Anda. Tidak ada biaya API, tidak ada tier rate limit, tidak perlu developer account. Mendukung search, membaca tweet, membaca profil, dan timeline.
</details>

<details>
<summary><strong>Bagaimana membaca konten XiaoHongShu / 小红书 secara programatik?</strong></summary>

Di desktop, gunakan **OpenCLI** (`agent-reach install --channels opencli`) — ia memakai ulang sesi login browser, jadi jika Anda pernah membuka XiaoHongShu, Anda siap; cukup satu klik di Chrome Web Store untuk memasang extension. Lalu gunakan `opencli xiaohongshu search "query"` / `opencli xiaohongshu note URL`. Di server, gunakan [xiaohongshu-mcp](https://github.com/xpzouying/xiaohongshu-mcp) (headless browser bawaan, QR login). Instalasi xhs-cli lama tetap bisa dipakai sebagai fallback backend (upstream tidak maintained sejak 2026-03, tidak direkomendasikan untuk setup baru).
</details>

---

## Kredit

[twitter-cli](https://github.com/public-clis/twitter-cli) · [rdt-cli](https://github.com/public-clis/rdt-cli) · [xhs-cli](https://github.com/jackwener/xiaohongshu-cli) · [bili-cli](https://github.com/public-clis/bilibili-cli) · [yt-dlp](https://github.com/yt-dlp/yt-dlp) · [Jina Reader](https://github.com/jina-ai/reader) · [Exa](https://exa.ai) · [mcporter](https://github.com/nicobailon/mcporter) · [feedparser](https://github.com/kurtmckee/feedparser) · [linkedin-scraper-mcp](https://github.com/stickerdaniel/linkedin-mcp-server)

## Kontak

- 📧 **Email:** pnt01@foxmail.com
- 🐦 **Twitter/X:** [@Neo_Reidlab](https://x.com/Neo_Reidlab)

Untuk kolaborasi atau pertanyaan, tambahkan saya di WeChat — saya akan mengundang Anda ke grup komunitas:

<p align="center">
  <img src="wechat-group-qr.jpg" width="280" alt="WeChat QR">
</p>

> Untuk laporan bug dan permintaan fitur, gunakan [GitHub Issues](https://github.com/Panniantong/Agent-Reach/issues) — lebih mudah dilacak.

## Lisensi

[MIT](../LICENSE)

## Teman

[OpenClaw di Tencent Cloud](https://www.tencentcloud.com/act/pro/intl-openclaw?referral_code=G76Y819A&lang=en&pg=) — OpenClaw sekali klik di Tencent Cloud: chat untuk menghubungkan Agent Reach & membuka kekuatan internet.

[AtomGit mirror](https://atomgit.com/qq_51337814/Agent-Reach) — Mirror AtomGit tersinkron untuk Agent Reach.

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=Panniantong/Agent-Reach&type=Date&v=20260309)](https://star-history.com/#Panniantong/Agent-Reach&Date)
