# AI 產業脈動雷達（radar）使用指南

一套「反資訊焦慮」系統：多平台收集 → 一頁排序 digest → 多學生起草 + 導師團批改
→ 自我迭代。所有輸出在 `~/.agent-reach/radar/`。

## 指令總覽

| 指令 | 作用 |
|---|---|
| `agent-reach radar [--print] [--deep-dive]` | 收集（Twitter 大神 / Exa / RSS / arXiv / Trends）→ 每日 digest |
| `agent-reach radar-deepdive [--top N]` | arXiv top 論文全文蒸餾成深讀報告（繁中） |
| `agent-reach radar-report [--student-model M]` | 學生們起草 → 助教評 → 主師評分出 gold |
| `agent-reach radar-students list\|add\|retire\|leaderboard` | 學生隊伍管理（汰舊換強） |
| `agent-reach radar-backfill [--handle H] [--repos R] [--distill]` | 大神歷史回溯 + 方法論知識庫蒸餾 |
| `agent-reach radar-evolve run\|freeze\|status` | autoresearch 式自我迭代迴圈 |
| `agent-reach kol-post <ticker>` | 單股 KOL 貼文鷹架 |

## 設定鍵（config.yaml 或同名大寫環境變數）

- `anthropic_api_key` — 主師（Fable 5）：批改、深讀、蒸餾、evolve。**radar 核心鍵**
- `openai_api_key` / `xai_api_key` — 助教 Codex / Grok（可選，缺了自動跳過）
- `radar_mentor_model` — 主師模型覆寫（預設 `claude-fable-5`）
- `radar_assistant_mentors` — 助教清單覆寫（預設 Opus / Sonnet / Codex / Grok）
- `ollama_base_url` — 學生端（預設 `http://127.0.0.1:11434`）
- `radar_output_dir` / `radar_sources_file` — 輸出與來源檔位置覆寫
- `twitter_auth_token` + `twitter_ct0` — 大神推文收集（Cookie-Editor 匯出）

## 來源調校：`~/.agent-reach/radar.yaml`

- `gurus:` 八類大神名單（godfathers / industry_leaders / research / engineering_oss /
  industry_supply / education_data / longform_voices / cn_ecosystem）。
  每人可帶 `lens`（怎麼讀透鏡，會出現在 digest 與學生材料中）、`rss`、`arxiv_names`
  （arXiv 作者加權）。自行增刪即可，defaults 會補齊缺的鍵。
- `arxiv_keywords:`（加權 dict）、`arxiv_categories`、`arxiv_orgs`、
  `arxiv_top_n`（進 digest 篇數）、`arxiv_deep_dive_n`（全文深讀篇數）。

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

1. 每晨 `agent-reach radar-report`（附帶產出 digest；讓 Claude 讀 gold + digest）
2. 每晨 `agent-reach radar-deepdive --top 3`
3. 每晚 `agent-reach radar-evolve run --budget 5`（有 fixtures 凍結後）
4. 每週看一次 `radar-students leaderboard` 與 `evolve/journal.md`
