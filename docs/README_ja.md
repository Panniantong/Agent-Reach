# Agent Reach Windows/Codex Fork

この fork は、Windows ネイティブの Codex 調査ワークフロー向けに対象を絞っています。

対応チャネル:

- `web` は Jina Reader
- `exa_search` は `mcporter`
- `github` は `gh`
- `youtube` は `yt-dlp`
- `rss` は `feedparser`
- `twitter` は任意導入の `twitter-cli`

## インストール

```powershell
uv tool install .
agent-reach install --env=auto
```

Twitter/X を追加する場合:

```powershell
agent-reach install --env=auto --channels=twitter
agent-reach configure twitter-cookies "auth_token=...; ct0=..."
```

ブラウザからの取り込みも使えます。

```powershell
agent-reach configure --from-browser chrome
```

## 確認

```powershell
agent-reach doctor
gh auth login
twitter status
```

`doctor` は、この fork がサポートする Windows/Codex 向けチャネルだけを表示します。
