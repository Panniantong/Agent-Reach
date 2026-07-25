<h1 align="center">👁️ Agent Reach</h1>

<p align="center">
  <strong>AIエージェントにワンクリックでインターネット全体へのアクセスを</strong>
</p>

<p align="center">
  <a href="../LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue.svg?style=for-the-badge" alt="MIT License"></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.10+-green.svg?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.10+"></a>
  <a href="https://github.com/Panniantong/agent-reach/stargazers"><img src="https://img.shields.io/github/stars/Panniantong/agent-reach?style=for-the-badge" alt="GitHub Stars"></a>
</p>

<p align="center">
  <a href="#クイックスタート">クイックスタート</a> · <a href="../README.md">中文</a> · <a href="README_en.md">English</a> · <a href="README_ko.md">한국어</a> · <a href="#対応プラットフォーム">プラットフォーム</a> · <a href="#設計思想">設計思想</a>
</p>

---

## なぜ Agent Reach？

AIエージェントはすでにインターネットにアクセスできます。しかし「ネットに繋がる」はほんの始まりに過ぎません。

最も価値のある情報は、さまざまなSNSやニッチなプラットフォームに散らばっています：Twitterの議論、Redditのフィードバック、YouTubeのチュートリアル、小紅書のレビュー、Bilibiliの動画、GitHubのアクティビティ… **これらこそ情報密度が最も高い場所です**。しかし、各プラットフォームにはそれぞれ障壁があります：

| 課題 | 現実 |
| ------ | ------ |
| Twitter API | 従量課金、中程度の利用で月額約$215 |
| Reddit | サーバーIPが403でブロックされる |
| 小紅書 | 閲覧にログインが必要 |
| Bilibili | 海外/サーバーIPをブロック |

エージェントをこれらのプラットフォームに接続するには、ツールを探し、依存関係をインストールし、設定をデバッグする必要があります — ひとつずつ。

**Agent Reach はこれを1つのコマンドにまとめます：**

```
Install Agent Reach: https://raw.githubusercontent.com/Panniantong/agent-reach/main/docs/install.md
```

これをエージェントにコピーするだけ。数分後には、ツイートの閲覧、Redditの検索、Bilibiliの視聴が可能になります。

**すでにインストール済み？1コマンドでアップデート：**

```
Update Agent Reach: https://raw.githubusercontent.com/Panniantong/agent-reach/main/docs/update.md
```

### ✅ 始める前に知っておきたいこと

| | |
| --- | --- |
| 💰 **完全無料** | すべてのツールはオープンソース、すべてのAPIは無料。唯一のコストはサーバープロキシ（月額$1）の可能性のみ — ローカルPCでは不要 |
| 🔒 **プライバシー安全** | Cookieはローカルに保存。アップロードされることはありません。完全オープンソース — いつでも監査可能 |
| 🔄 **常に最新** | 上流ツール（yt-dlp、twitter-cli、rdt-cli、Jina Reader等）を定期的に追跡・更新 |
| 🤖 **あらゆるエージェントに対応** | Claude Code、OpenClaw、Cursor、Windsurf… コマンドを実行できるすべてのエージェント |
| 🩺 **組み込み診断** | `agent-reach doctor` — 1コマンドで何が動き、何が動かないか、どう修正するかを表示 |

---

## 対応プラットフォーム

| プラットフォーム | 機能 | セットアップ | 備考 |
| ----------------- | ------ | :----------: | ------ |
| 🌐 **Web** | 閲覧 | 設定不要 | 任意のURL → クリーンなMarkdown（[Jina Reader](https://github.com/jina-ai/reader) ⭐9.8K） |
| 🐦 **Twitter/X** | 閲覧・検索 | 設定不要 / Cookie | 単一ツイートはすぐに閲覧可能。Cookieで検索、タイムライン、投稿が解放（[twitter-cli](https://github.com/public-clis/twitter-cli)） |
| 📕 **小紅書** | 閲覧・検索・コメント | OpenCLI / Cookie | OpenCLI はユーザー管理の既存 Chrome セッションだけを使用。MCP/旧ツールは Cookie-Editor を使用 |
| 🎵 **抖音** | 動画解析・ウォーターマークなしダウンロード | mcporter | [douyin-mcp-server](https://github.com/yzfly/douyin-mcp-server)、ログイン不要 |
| 💼 **LinkedIn** | Jina Reader（公開ページ） | プロフィール、企業、求人検索 | エージェントに「LinkedInの設定を手伝って」と伝えてください |
| 💬 **WeChat記事** | 検索 + 閲覧 | 設定不要 | WeChat公式アカウント記事の検索+閲覧（完全Markdown）（[Exa](https://exa.ai) + [Camoufox](https://github.com/daijro/camoufox)（オプション）） |
| 📰 **Weibo** | トレンド・検索・フィード・コメント | 設定不要 | ホット検索、コンテンツ/ユーザー/トピック検索、フィード、コメント（[mcp-server-weibo](https://github.com/Panniantong/mcp-server-weibo)） |
| 💻 **V2EX** | 人気トピック・ノードトピック・トピック詳細+返信・ユーザープロフィール | 設定不要 | 公開JSON API、認証不要。技術コミュニティのコンテンツに最適 |
| 💬 **Linux.do** | 人気トピック・スレッド・返信・キャッシュ検索 | オプション | `agent-reach install --channels=linuxdo`。ブラウザフォールバックはChromiumをダウンロードします |
| 📈 **雪球（Xueqiu）** | 株価・検索・人気投稿・人気銘柄 | 設定不要 | 公開APIで自動セッションCookie、ログイン不要 |
| 🎙️ **小宇宙Podcast** | 文字起こし | 無料APIキー | Podcast音声 → Groq Whisper（無料）による完全テキスト文字起こし |
| 🔍 **Web検索** | 検索 | 自動設定 | インストール時に自動設定、無料、APIキー不要（[Exa](https://exa.ai)、[mcporter](https://github.com/nicepkg/mcporter)経由） |
| 📦 **GitHub** | 閲覧・検索 | 設定不要 | [gh CLI](https://cli.github.com) 搭載。公開リポジトリはすぐ使える。`gh auth login`でFork、Issue、PRが解放 |
| 📺 **YouTube** | 閲覧・**検索** | 設定不要 | 字幕 + 1800以上の動画サイトでの検索（[yt-dlp](https://github.com/yt-dlp/yt-dlp) ⭐148K） |
| 📺 **Bilibili** | 閲覧・**検索** | 設定不要 | [bili-cli](https://github.com/public-clis/bilibili-cli) で検索・動画情報（ログイン不要）、字幕は OpenCLI。yt-dlp は Bilibili の 412 制限により使用しません |
| 📡 **RSS** | 閲覧 | 設定不要 | 任意のRSS/Atomフィード（[feedparser](https://github.com/kurtmckee/feedparser) ⭐2.3K） |
| 📖 **Reddit** | 検索・閲覧 | Cookie | 2024年以降認証が必要 — インストール後 `rdt login` を実行（[rdt-cli](https://github.com/public-clis/rdt-cli)） |

> **セットアップレベル：** 設定不要 = インストールしてすぐ使える · 自動設定 = インストール時に処理 · mcporter = MCPサービスが必要 · Cookie = ブラウザからエクスポート · プロキシ = 月額$1

---

## クイックスタート

以下をAIエージェント（Claude Code、OpenClaw、Cursor等）にコピーしてください：

```
Install Agent Reach: https://raw.githubusercontent.com/Panniantong/agent-reach/main/docs/install.md
```

エージェントが自動でインストールし、環境を検出し、何が使えるかを教えてくれます。

> 🔄 **すでにインストール済み？** 1コマンドでアップデート：
>
> ```
> Update Agent Reach: https://raw.githubusercontent.com/Panniantong/agent-reach/main/docs/update.md
> ```

<details>
<summary>手動インストール</summary>

```bash
pip install https://github.com/Panniantong/agent-reach/archive/main.zip
agent-reach install --env=auto
```

</details>

<details>
<summary>Skillとしてインストール（Claude Code / OpenClaw / Skills対応の任意のエージェント）</summary>

```bash
npx skills add Panniantong/Agent-Reach@agent-reach
```

Skillインストール後、エージェントは`agent-reach` CLIが利用可能かを自動検出し、必要に応じてインストールします。

> `agent-reach install` でインストールした場合、Skillは自動的に登録されます — 追加の手順は不要です。
</details>

---

## すぐに使える機能

設定不要 — エージェントに伝えるだけ：

- 「このリンクを読んで」→ `curl https://r.jina.ai/URL` で任意のWebページ
- 「このGitHubリポジトリは何？」→ `gh repo view owner/repo`
- 「この動画の内容は？」→ `yt-dlp --dump-json URL` で字幕取得
- 「このツイートを読んで」→ `TWITTER_AUTH_TOKEN` / `TWITTER_CT0` を設定してから `twitter tweet URL`
- 「このRSSを購読して」→ `feedparser` でフィード解析
- 「GitHubでLLMフレームワークを検索して」→ `gh search repos "LLM framework"`

**コマンドを覚える必要はありません。** エージェントがSKILL.mdを読み、何を呼び出すべきか理解します。

---

## 必要に応じてアンロック

使わない？設定しなくてOK。すべてのステップはオプションです。

### 🍪 Cookie — 無料、2分

エージェントに「Twitterのクッキーの設定を手伝って」と伝えてください —
Cookie-Editor による手動エクスポートを案内します。保存した値は
`agent-reach doctor` が設定の有無を確認するためだけに使われ、doctor は
`twitter status` を実行しません。上流の `twitter` コマンドには
`TWITTER_AUTH_TOKEN` と `TWITTER_CT0` を明示的に設定してください。

### 🌐 プロキシ — 月額$1、サーバーのみ

通常はプロキシ不要です。ネットワーク上で Reddit/Twitter が遮断されている場合のみ、プロキシを設定してください。Bilibili は bili-cli を使用します。

> ローカルPCではプロキシは不要です。Reddit検索はプロキシなしでもrdt-cliで無料で動作します。

---

## 一目でわかるステータス

```
$ agent-reach doctor

👁️  Agent Reach ステータス
========================================

✅ 利用可能:
  ✅ GitHubリポジトリとコード — 公開リポジトリの閲覧・検索可能
  ✅ YouTube動画字幕 — yt-dlp
  ✅ Bilibili検索・動画情報 — bili-cli（字幕は OpenCLI）
  ✅ RSS/Atomフィード — feedparser
  ✅ Webページ（任意のURL） — Jina Reader API

🔍 検索（無料Exaキーで解放）:
  ⬜ Webセマンティック検索 — exa.aiで無料キーを取得

🔧 設定可能:
  ⚠️  Twitter/X — doctor は明示的な認証情報の有無だけを確認。上流CLIには環境変数が必要
  ✅ Reddit投稿とコメント — rdt-cliで検索+閲覧（無料、プロキシ不要）
  ⬜ 小紅書ノート — OpenCLI は既存セッションのみ。それ以外は Cookie-Editor で MCP/旧ツールを設定

ステータス: 9チャンネル中6チャンネルが利用可能
```

---

## 設計思想

**Agent Reach はスキャフォールディングツールであり、フレームワークではありません。**

新しいエージェントを立ち上げるたびに、ツールを探し、依存関係をインストールし、設定をデバッグする時間がかかります — Twitterを読むには何を使う？Redditのブロックをどう回避する？YouTubeの字幕をどう抽出する？毎回、同じ作業を繰り返すことになります。

Agent Reach はシンプルなことを1つだけ行います：**ツールの選定と設定の判断をあなたの代わりに行います。**

インストール後、エージェントは上流ツール（twitter-cli、rdt-cli、xhs-cli、yt-dlp、mcporter、gh CLI等）を直接呼び出します — 間にラッパーレイヤーはありません。

### 🔌 すべてのチャンネルはプラグ可能

各プラットフォームは上流ツールに対応しています。**気に入らなければ差し替えるだけ。**

```
channels/
├── web.py          → Jina Reader     ← Firecrawl、Crawl4AIなどに差し替え可能…
├── twitter.py      → twitter-cli      ← 公式APIなどに差し替え可能…
├── youtube.py      → yt-dlp          ← YouTube API、Whisperなどに差し替え可能…
├── github.py       → gh CLI          ← REST API、PyGithubなどに差し替え可能…
├── bilibili.py     → bili-cli ▸ OpenCLI ▸ 検索 API（yt-dlp は 412 制限により退役）
├── reddit.py       → OpenCLI ▸ rdt-cli（ログイン状態が必要）
├── linuxdo.py      → linuxdo-reader CLI（独立したPython 3.11+ uv tool）
├── xiaohongshu.py  → OpenCLI ▸ xiaohongshu-mcp ▸ xhs-cli
├── douyin.py       → mcporter MCP    ← 他の抖音ツールに差し替え可能…
├── linkedin.py     → linkedin-mcp    ← LinkedIn APIに差し替え可能…
├── rss.py          → feedparser      ← atomaなどに差し替え可能…
├── exa_search.py   → mcporter MCP    ← Tavily、SerpAPIなどに差し替え可能…
└── __init__.py     → チャンネルレジストリ（doctor チェック用）
```

各チャンネルファイルは、上流ツールがインストールされ動作しているかをチェックするだけです（`agent-reach doctor` 用の `check()` メソッド）。実際の閲覧や検索は上流ツールを直接呼び出して行います。

### 現在のツール選定

| シナリオ | ツール | 理由 |
| ---------- | -------- | ------ |
| Webページ閲覧 | [Jina Reader](https://github.com/jina-ai/reader) | ⭐9.8K、無料、APIキー不要 |
| ツイート閲覧 | [twitter-cli](https://github.com/public-clis/twitter-cli) | 2.1K Star、Cookie認証、検索/閲覧/タイムライン/長文 |
| YouTube 字幕 + 検索 | [yt-dlp](https://github.com/yt-dlp/yt-dlp) | YouTube と対応動画サイト向け（Bilibili には使用しません） |
| Bilibili | [bili-cli](https://github.com/public-clis/bilibili-cli) ▸ OpenCLI ▸ 検索 API | yt-dlp は 412 制限で退役。bili-cli はログイン不要で検索・閲覧可能 |
| Web検索 | [Exa](https://exa.ai)（[mcporter](https://github.com/nicepkg/mcporter)経由） | AIセマンティック検索、MCP統合、APIキー不要 |
| GitHub | [gh CLI](https://cli.github.com) | 公式ツール、認証後フルAPI |
| RSS閲覧 | [feedparser](https://github.com/kurtmckee/feedparser) | Pythonエコシステムの標準、⭐2.3K |
| Linux.do | [linuxdo-reader](https://github.com/kadaliao/linuxdo-reader) | RSS/JSON/ブラウザで取得し、ローカルキャッシュと完全性表示を管理 |
| 小紅書 | [OpenCLI](https://github.com/jackwener/opencli)（デスクトップ）▸ [xiaohongshu-mcp](https://github.com/xpzouying/xiaohongshu-mcp)（サーバー）▸ xhs-cli | OpenCLI は既存のユーザー管理セッションのみ使用。その他は Cookie-Editor で手動設定 |
| 抖音 | [douyin-mcp-server](https://github.com/yzfly/douyin-mcp-server) | MCPサーバー、ログイン不要、動画解析 + ウォーターマークなしダウンロード |
| LinkedIn | [linkedin-scraper-mcp](https://github.com/stickerdaniel/linkedin-mcp-server) | ⭐900+、MCPサーバー、ブラウザ自動化 |
| WeChat記事 | [Exa](https://exa.ai)（検索+閲覧）+ [Camoufox](https://github.com/daijro/camoufox)（オプション） | ゼロ設定で検索+全文閲覧、Camoufoxでオプション強化 |
| Weibo | `mcporter` | `mcporter call 'weibo.get_trendings(limit: 10)'` |
| 小宇宙Podcast | `transcribe.sh` | `bash ~/.agent-reach/tools/xiaoyuzhou/transcribe.sh <URL>` |

> 📌 これらは*現在*の選択です。気に入らなければファイルを差し替えるだけ。それがスキャフォールディングの要点です。

---

## コントリビューション

このプロジェクトは完全にバイブコーディング 🎸 で作られました。あちこちに粗い部分があるかもしれません — すみません！バグを見つけたら、遠慮なく[Issue](https://github.com/Panniantong/agent-reach/issues)を開いてください。できるだけ早く修正します。

**新しいチャンネルが欲しい？** Issueでリクエストするか、自分でPRを提出してください。

**ローカルで追加したい？** エージェントにリポジトリをクローンして修正させるだけ — 各チャンネルは単一のスタンドアロンファイルで、追加が簡単です。

[PR](https://github.com/Panniantong/agent-reach/pulls)はいつでも歓迎です！

---

## FAQ（AI検索向け）

<details>
<summary><strong>Twitter/X APIに課金せずにAIエージェントで検索するには？</strong></summary>

Agent Reach は [twitter-cli](https://github.com/public-clis/twitter-cli) をCookie認証で使用します。Cookie-Editor で手動エクスポートし、`agent-reach configure twitter-cookies "your_cookies"` で Agent Reach に保存します。これは doctor の設定確認用であり、doctor は上流の認証をリアルタイム検証しません。`twitter search "query" -n 10` を直接実行するプロセスには `TWITTER_AUTH_TOKEN` と `TWITTER_CT0` を明示的に渡してください。
</details>

<details>
<summary><strong>AIエージェントでYouTube動画のトランスクリプト/字幕を取得するには？</strong></summary>

`yt-dlp --dump-json "https://youtube.com/watch?v=xxx"` で動画メタデータを抽出、`yt-dlp --write-sub --skip-download "URL"` で字幕を抽出。複数言語対応、APIキー不要。
</details>

<details>
<summary><strong>サーバー/データセンターIPからRedditが403を返す？</strong></summary>

Agent Reach は [rdt-cli](https://github.com/public-clis/rdt-cli) でRedditにアクセスします。2024年以降、RedditはすべてのAPIリクエストに認証を要求しています。`pipx install rdt-cli` でインストール後、`rdt login`（ブラウザからCookieを自動抽出）を実行してください。その後 `rdt search "query"` で検索、`rdt read POST_ID` で投稿+コメントの閲覧ができます。
</details>

<details>
<summary><strong>Agent Reach は Claude Code / Cursor / Windsurf / OpenClaw で動作する？</strong></summary>

はい！Agent Reach はインストーラー + 設定ツールです。シェルコマンドを実行できるあらゆるAIコーディングエージェントで使用できます — Claude Code、Cursor、Windsurf、OpenClaw、Codex等。`pip install agent-reach` を実行し、`agent-reach install` を実行するだけで、エージェントはすぐに上流ツールを使い始められます。
</details>

<details>
<summary><strong>Agent Reach は無料？APIのコストは？</strong></summary>

100%無料でオープンソース。すべてのバックエンド（twitter-cli、rdt-cli、OpenCLI、bili-cli、yt-dlp、Jina Reader、Exa）は有料APIキーが不要な無料ツールです。ネットワーク上で特定サイトが遮断されている場合のみ、プロキシ費用が発生することがあります。
</details>

<details>
<summary><strong>Twitter APIの無料代替 — Webスクレイピング用</strong></summary>

Agent Reach はtwitter-cliを使用し、Cookie認証でTwitterにアクセスします — ブラウザセッションと同じです。API料金なし、レート制限のティアなし、開発者アカウント不要。検索、ツイート閲覧、プロフィール閲覧、タイムラインに対応。
</details>

<details>
<summary><strong>小紅書のコンテンツをプログラムで読むには？</strong></summary>

Agent Reach は小紅書へのログインを代行せず、ブラウザ Cookie も読み取りません。OpenCLI はユーザーが既に所有・管理している Chrome セッションだけを使用します。既存セッションがない場合は自動ログインせず、Cookie-Editor で手動エクスポートして xiaohongshu-mcp または旧ツールを設定してください。`agent-reach configure xhs-cookies` は OpenCLI / Chrome に Cookie を注入しません。
</details>

<details>
<summary><strong>AIエージェントで抖音の動画を解析するには？</strong></summary>

douyin-mcp-serverをインストールすれば、`mcporter call 'douyin.parse_douyin_video_info(share_link: "share_url")'` で動画情報を解析し、ウォーターマークなしのダウンロードリンクを取得できます。ログイン不要 — 抖音のリンクを共有するだけ。詳細は <https://github.com/yzfly/douyin-mcp-server> を参照。
</details>

---

## クレジット

[twitter-cli](https://github.com/public-clis/twitter-cli) · [rdt-cli](https://github.com/public-clis/rdt-cli) · [xhs-cli](https://github.com/jackwener/xiaohongshu-cli) · [Jina Reader](https://github.com/jina-ai/reader) · [yt-dlp](https://github.com/yt-dlp/yt-dlp) · [Exa](https://exa.ai) · [feedparser](https://github.com/kurtmckee/feedparser) · [douyin-mcp-server](https://github.com/yzfly/douyin-mcp-server) · [linkedin-scraper-mcp](https://github.com/stickerdaniel/linkedin-mcp-server)

## お問い合わせ

- 📧 **メール:** <pnt01@foxmail.com>
- 🐦 **Twitter/X:** [@Neo_Reidlab](https://x.com/Neo_Reidlab)

コラボレーションやご質問は、WeChatで追加してください — コミュニティグループにご招待します：

<p align="center">
  <img src="wechat-group-qr.jpg" width="280" alt="WeChat QR">
</p>

> バグ報告や機能リクエストは [GitHub Issues](https://github.com/Panniantong/Agent-Reach/issues) をご利用ください — 追跡が容易です。

## ライセンス

[MIT](../LICENSE)

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=Panniantong/Agent-Reach&type=Date&v=20260309)](https://star-history.com/#Panniantong/Agent-Reach&Date)
