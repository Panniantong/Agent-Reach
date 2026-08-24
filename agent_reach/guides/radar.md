# AI 產業脈動雷達（radar）使用指南

一套「反資訊焦慮」的資料綜合收集器：多平台複選收集（含 arXiv 五主題垂直、Finviz
市場訊號）→ 一頁排序 digest → 主題 wiki 知識庫 → NotebookLM 同步 → 場景 pipeline
（專家長報告 / 大神總結 / 雙語社群貼文草稿）→ 多學生起草 + 導師團批改 → 自我迭代。
所有輸出在 `~/.agent-reach/radar/`。

## 指令總覽

| 指令 | 作用 |
|---|---|
| `agent-reach radar [--print] [--deep-dive] [--platforms a,b]` | 收集（Twitter 大神 / Exa / RSS / arXiv / Trends / Finviz）→ 每日 digest |
| `agent-reach radar-deepdive [--top N] [--topic T]` | arXiv top 論文全文蒸餾成深讀報告（繁中） |
| `agent-reach radar-wiki update\|promote\|status [--topic T]` | 主題 wiki：LLM 起草 → 人審 → commit |
| `agent-reach radar-sync run\|setup\|status [--topic T] [--dry-run]` | 推送論文/深讀到每主題 NotebookLM notebook |
| `agent-reach radar-run list\|providers\|<場景id> [--set k=v]` | 場景 pipeline 觸發 + provider 健康檢查 |
| `agent-reach radar-ui [--port 8123]` | 暗黑極客 web 控制台（瀏覽 + 一鍵觸發） |
| `agent-reach radar-narrative ingest\|discover\|contract\|forecast\|resolve\|calibrate\|status` | 證據覆核、事件契約、校準機率與追加式結算 |
| `agent-reach radar-report [--student-model M]` | 學生們起草 → 助教評 → 主師評分出 gold |
| `agent-reach radar-students list\|add\|retire\|leaderboard` | 學生隊伍管理（汰舊換強） |
| `agent-reach radar-backfill [--handle H] [--repos R] [--distill]` | 大神歷史回溯 + 方法論知識庫蒸餾 |
| `agent-reach radar-evolve run\|freeze\|status` | autoresearch 式自我迭代迴圈 |
| `agent-reach kol-post <ticker>` | 單股 KOL 貼文鷹架 |

## 設定鍵（config.yaml 或同名大寫環境變數）

- `anthropic_api_key` — 主師（Fable 5）：批改、深讀、蒸餾、wiki、evolve。**radar 核心鍵**
- `openai_api_key` / `xai_api_key` — 助教 Codex / Grok（可選，缺了自動跳過）
- `nvidia_api_key` — NVIDIA NIM（Nemotron 場景；build.nvidia.com 取得）
- `radar_mentor_model` — 主師模型覆寫（預設 `claude-fable-5`）
- `radar_assistant_mentors` — 助教清單覆寫（預設 Opus / Sonnet / Codex / Grok）
- `ollama_base_url` — 學生端 + 本地場景模型（預設 `http://127.0.0.1:11434`）
- `radar_output_dir` / `radar_sources_file` — 輸出與來源檔位置覆寫
- `narrative_data_dir` — 敘事 SQLite 與不可變 blobs 位置覆寫
- `quant_data_root` — 只讀 Quant artifact 根目錄（預設 `D:\DOT\Quant\data`）
- `twitter_auth_token` + `twitter_ct0` — 大神推文收集（Cookie-Editor 匯出）
- `finviz_auth_token` — Finviz Elite（或走 `finviz_env_paths` env 檔）
- `notebooklm_profile` — NotebookLM 登入 profile（通常 `default`）

## 來源調校：`~/.agent-reach/radar.yaml`

- `gurus:` 八類大神名單（godfathers / industry_leaders / research / engineering_oss /
  industry_supply / education_data / longform_voices / cn_ecosystem）。
  每人可帶 `lens`（怎麼讀透鏡，會出現在 digest 與學生材料中）、`rss`、`arxiv_names`
  （arXiv 作者加權）。自行增刪即可，defaults 會補齊缺的鍵。
- `arxiv_keywords:`（加權 dict）、`arxiv_categories`、`arxiv_orgs`、
  `arxiv_top_n`（進 digest 篇數）、`arxiv_deep_dive_n`（全文深讀篇數）。

## 多主題垂直（EE / RF / AI / Spacetech / Quantum）

`topics:` 讓 arXiv 掃描一主題一查詢（查詢間自動間隔 ≥3s，符合 arXiv 禮儀），
論文帶 `topic` 標籤、digest 分主題小節、跨主題自動去重：

```yaml
topics:
  ee:
    label: "電子工程 / 半導體"
    arxiv_categories: [eess.SY, cs.AR, cs.ET, physics.app-ph]
    arxiv_keywords: {chiplet: 3, advanced packaging: 3, hbm: 3}
```

注意：radar.yaml 是 shallow merge——自訂 `topics` 會**整組取代**預設五主題；
刪掉整個 `topics` 鍵則回退到頂層 `arxiv_categories`（legacy 單查詢）。
平台複選：`agent-reach radar --platforms arxiv,finviz` 只跑選中的收集器。

## Wiki 知識庫（每主題一頁，人工把關）

泛化 karpathy.md 的流程：敘事區由 LLM merge-rewrite（有上限），
`## 里程碑論文索引` 由程式碼確定性維護（去重、上限 100 條）。

```bash
agent-reach radar-wiki update --topic quantum   # 起草 → radar/wiki/drafts/
# 審核 draft 內容後：
agent-reach radar-wiki promote --topic quantum  # 覆蓋 knowledge/wiki/quantum.md
git diff agent_reach/knowledge/wiki/            # 人工審 diff，滿意再 commit
```

wiki 的 `## 精要規則` 會自動注入該主題深讀報告的 system prompt（只有方法、無事實）。
無 `ANTHROPIC_API_KEY` 時 draft 是 PENDING 鷹架，讓互動式 Claude 補完。

## NotebookLM 同步（每主題一個 notebook）

```bash
pip install "agent-reach[notebooklm]"                       # 釘版 notebooklm-py
notebooklm login --master-token --account you@gmail.com     # 一次性，之後可無人值守
agent-reach radar-sync setup                                # 驗證就緒
agent-reach radar-sync run --topic ee --dry-run             # 先看計畫
agent-reach radar-sync run                                  # 高分論文 add_url + 深讀 add_text
```

- 逼近帳號來源上限時自動分片新 notebook（`EE-2026Q3` → `EE-2026Q3-MMDD`）
- 去重雙保險：本地 `state.json` + key 嵌在來源標題（重跑不重複推）
- 上游是非官方 API（Google 可能改），版本釘死在 extra 裡，壞了只影響此功能

## Finviz 市場訊號

Token 依序解析：`FINVIZ_AUTH_TOKEN` env → config `finviz_auth_token` →
`finviz_env_paths` 列的 env 檔中的 `FINVIZ_AUTH_TOKEN=` 行。**永不打印**。
（提醒：舊 token 若曾以明文存檔，先去 Finviz rotate。）
`export/news` 市場新聞過 topic 關鍵字閘；`export/groups` 板塊單日 |漲跌| 超過
`finviz.sector_alert_pct`（預設 1.5%）就進 digest「📊 市場訊號」。

## 場景 pipeline（radar-run / 控制台觸發）

```bash
agent-reach radar-run providers          # 各 provider 健康（含 Ollama 已 pull 模型）
agent-reach radar-run list               # 場景 + 就緒狀態
agent-reach radar-run arxiv_expert_report --set topic=ee --set top_n=2
agent-reach radar-run x_guru_summary --set category=research
agent-reach radar-run github_trending_post --set days=7 --set keyword=agent
agent-reach radar-run market_signal_post
```

- 模型 spec 格式 `provider:model`：`ollama:qwen3:4b`（本地）、
  `nvidia:nvidia/llama-3.3-nemotron-super-49b-v1.5`（NIM）、`anthropic:claude-fable-5`
- 預設在 radar.yaml `scenario_models:`（list = 依序 fallback），`--set model=` 單次覆寫
- 社群貼文一律**雙語草稿**（`## 繁中版` + `## English`）寫進 `radar/social/`，
  人工審核後才發，recommend-only

## 控制台（radar-ui）

```bash
pip install "agent-reach[ui,narrative]"
agent-reach radar-ui        # http://127.0.0.1:8123，僅本機
```

頂欄 provider 狀態燈；左欄瀏覽 DIGEST/DEEPDIVE/REPORTS/SUMMARIES/SOCIAL/WIKI；
中央 markdown 閱讀器（j/k 移動、Enter 開啟）；右欄 TRIGGER DECK——COLLECT 卡
複選平台一鍵收集，場景卡缺 provider 會置灰並標明缺什麼；底部 console 即時串流
job log。


1.7.0 起控制台加入總覽、產業、公司、來源、歷史、推演、結算、校準八個工作區；
未通過校準閘門的局面不顯示數字機率。完整流程與事件 sample 格式見
[`narrative.md`](narrative.md)。
## 學生隊伍（汰舊換強）

種子是 2 位 `qwen3:4b` 不同 persona。新開源小模型上場：

```bash
ollama pull nemotron-mini
agent-reach radar-students add --id nemotron-1 --model nemotron-mini --persona "工程細節型"
# 跑幾天 radar-report 累積成績後：
agent-reach radar-students leaderboard   # rolling mean 落後榜首太多會出退役建議
agent-reach radar-students retire --id qwen3-4b-macro --reason "被 nemotron 取代"
```

退役永遠人工確認（避免抽樣噪聲錯殺），歷史成績保留在 `scores.jsonl`。

## 自我迭代（evolve）

借 karpathy/autoresearch：固定評測 + 短實驗 + 自動保留/丟棄。

```bash
# 先跑幾天 radar-report 累積 training 材料，然後凍結評測基準：
agent-reach radar-evolve freeze --from-training 5   # 之後 commit evolve/fixtures/
# 過夜跑（一次一變因，pytest→health→評分三道閘，贏 base+epsilon 才保留）：
agent-reach radar-evolve run --budget 5
agent-reach radar-evolve status                      # 或看 evolve/journal.md
```

- 三檔分離：`radar_evolve.py`（固定 harness，hash 防竄改）/ 允許清單檔案（agent 改）/
  `evolve/program.md`（只有你能改：目標、硬規則、假設 backlog）
- 保留的實驗 fast-forward 進 `radar-evolve` branch —— **合進 main 永遠由你開 PR**
- 隨時叫停：`touch evolve/STOP`

## 建議節奏（cron / 排程）

1. 每晨 `agent-reach radar`（全平台收集，含 finviz）→ `radar-deepdive --top 3`
   → `radar-wiki update` → `radar-sync run`（收集鏈共用 latest-items.json，arXiv 只打一次）
2. 每晨 `agent-reach radar-report`（讓 Claude 讀 gold + digest）
3. 想要時從控制台（`radar-ui`）或 `radar-run` 手動觸發專家長報告 / 大神總結 / 貼文草稿
4. 每晚 `agent-reach radar-evolve run --budget 5`（有 fixtures 凍結後）
5. 每週看一次 `radar-students leaderboard`、`evolve/journal.md`，並審 promote 的 wiki diff
