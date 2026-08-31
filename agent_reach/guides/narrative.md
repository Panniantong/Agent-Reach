# 敘事推演與校準機率

`radar-narrative` 把外部觀點拆成可覆核主張，再連到只讀 Quant artifact、事件契約、
時間外校準與追加式結算。它是研究工作台，不建立部位、訂單或交易指令。

## 安裝與資料位置

```bash
pip install "agent-reach[ui,narrative]"
agent-reach radar-ui
```

開啟 `http://127.0.0.1:8123`。切到「研究」可使用 Themes、Company、Briefs、
Reports、Watchlist、Live 與 Monitor；切到「推演」則載入 NVDA 的結果盤。
研究頁可在 Chain、Graph、Scenario 三種視圖間切換，所有 pack 都顯示 as-of、
coverage、證據等級、瓶頸契約與版本差異。推演頁預設直接載入 NVDA 的結果盤，
先顯示體制、歷史韻腳、Quant 證據帶、可重疊局面、支持／反證、失效條件與
受益／受害對象；原文匯入、事件契約與校準工具收在結果下方的工作台。

系統內建的局面是研究 blueprint，不是已校準預測。若帳本沒有通過發布閘門的
forecast，局面仍會完整顯示，但機率只顯示「資料不足」。已建立且通過閘門的
事件契約會併入同一張結果盤，並顯示機率與區間。

- 結構化資料：`~/.agent-reach/radar/narrative/narrative.sqlite3`
- 不可變原文：`~/.agent-reach/radar/narrative/blobs/<sha256>.<ext>`
- Quant 根目錄：預設 `D:\DOT\Quant\data`，只讀
- 設定覆寫：`narrative_data_dir`、`quant_data_root`
- SQLite schema 目前為 v3，由 `PRAGMA user_version` 管理；升級前會留下
  `narrative.sqlite3.pre-v3.bak`，較新且不相容的 schema 會拒絕開啟

研究引擎的 TradingView 輸入固定在
`D:\DOT\Quant\data\tradingview\2026Q2PIT`，Finviz 固定在
`D:\DOT\Quant\data\finviz`。缺檔只形成 coverage gap，不會向根目錄外尋找替代檔。

## 證據規則

流程固定為：

```text
來源原文 → 可驗證主張 → Quant 數據 → 因果驅動 → 事件契約 → 校準機率 → 結算
```

新匯入主張一律是 `GUESS / LOW / pending`。只有下列其中之一成立才能標為
`verified`：

1. 已驗證的 Quant 或官方證據；
2. 兩個獨立可靠二手來源互證。

`FRAME` 與 `GUESS` 的信心不得高於 LOW。Serenity 與黃靖哲是不同來源身分；
邦妮區塊鏈與科幣託預設帶 `affiliate_exchange` 利益衝突標記。
`AIbubble.md`、`light.md`、`musk.md`、`robots.md` 透過
`seed-reports` 匯入時仍留在待驗證隔離層。

探索必須由使用者主動觸發。Exa 結果只進 `discovery_candidates` 待審表；
核准並匯入後也仍須逐項覆核 claim，搜尋排名不是證據。

## CLI 工作流

匯入文字、URL 或檔案：

```bash
agent-reach radar-narrative ingest --text "..." --ticker NVDA --domain information-technology
agent-reach radar-narrative ingest --url "https://..." --source-id stratechery
agent-reach radar-narrative ingest --file note.pdf --ticker NVDA
agent-reach radar-narrative discover --query "NVDA AI infrastructure demand" --count 8
```

建立事件契約。各局面可以重疊，邊際機率不必加總為 100%；聯合局面必須建立含
依賴／共現特徵的獨立契約：

```json
{
  "scope_type": "ticker",
  "scope_id": "NVDA",
  "domain": "information-technology",
  "horizon": "1y",
  "statement": "NVDA 在結算日收盤高於 200",
  "resolution_date": "2027-06-30",
  "resolution_source": "quant_prices",
  "criteria": {"operator": "price_above", "threshold": 200},
  "source_ids": ["serenity_aleabitoreddit"],
  "dependency_ids": []
}
```

```bash
agent-reach radar-narrative contract --payload contract.json
agent-reach radar-narrative forecast --contract-id evt_... --samples samples.json --features current.json
agent-reach radar-narrative resolve --contract-id evt_...
agent-reach radar-narrative resolve --contract-id evt_... --outcome 1 --reason "官方拆股調整" --actor analyst
agent-reach radar-narrative calibrate --domain information-technology --horizon 1y
agent-reach radar-narrative status --json
```

Serenity 與產業研究工作流：

```bash
agent-reach radar-narrative serenity-backfill --days 90 --count 2000
agent-reach radar-narrative serenity-backfill --days 90 --count 2000 \
  --serenity-jsonl "D:\\path\\to\\x_subs_downloader\\posts.jsonl"
agent-reach radar-narrative serenity-methodology --min-posts 2 --json
agent-reach radar-narrative research --slice cpo-external-laser --as-of 2026-08-30
agent-reach radar-narrative daily-sync --serenity-days 2
agent-reach radar-narrative weekly-freeze --as-of 2026-08-30
agent-reach radar-narrative pack-diff --pack-id pack_... --base-pack-id pack_...
agent-reach radar-narrative relationship-calibrate --horizon 1y
agent-reach radar-narrative sec-sync --ticker LITE --as-of 2026-08-30 \
  --user-agent "Agent Reach analyst@example.com" --count 40
agent-reach radar-narrative policy-sync --query "export controls" --as-of 2026-08-30
```

`serenity-backfill` 排除純轉貼，以 tweet URL／內容雜湊去重；原文與可選的繁中、
英文翻譯存在同一 document，翻譯不建立第二份證據。沒有 X archive/export 時，
每日 coverage 的零表示 unknown，不表示當日沒有貼文。MethodProfile 固定先進 draft，
沒有 analyst voting weight。

`--serenity-jsonl` 只讀取 `x_subs_downloader` README 公開定義的
`id/timestamp/images/en/zh` JSONL，不執行或修改下載器，也不讀取
`chrome_profile`。其中 `en` 是證據原文，`zh` 只作翻譯展示；匯入結果與
`twitter-cli user-posts` 依貼文 URL 去重。下載器本身固定把 profile、log 與輸出寫在
自己的目錄，而且要求互動登入，因此 Agent Reach 不代為啟動。`serenity-methodology`
只把跨至少兩篇獨立原貼的字面訊號列為待人工核准候選；共現不能建立因果順序。

`sec-sync` 只接受 SEC 的 submissions 與 Archives 公開端點，保存 10-K、10-Q、
8-K、20-F、6-K 及其 `/A` 修正版的 accession、filing date、available date、原文
與 hash。SEC 要求帶聯絡方式的 descriptive User-Agent；可用 `sec_user_agent` 設定，
或每次傳 `--user-agent`。`policy-sync` 保存 Federal Register 的 proposed、final、
effective 狀態。Congress.gov 具名法案與 Regulations.gov docket 可由
`/official/congress`、`/official/regulations` 主動同步；歷史截止日後才更新的 payload
會被 PIT 排除。這些來源只證明官方文件及其狀態存在，不會自動建立公司影響 claim。

歷史 sample 格式：

```json
{
  "samples": [
    {
      "as_of": "2023-01-31",
      "outcome_observed_at": "2024-01-31",
      "outcome": 1,
      "features": {"revenue_growth": 0.31, "price_return_63d": 0.12}
    }
  ]
}
```

features 只接受當時已知的 numeric 值。`probability`、`forecast`、
`signal`、`target` 等結果型欄位會被拒絕。

## 機率發佈閘門

模型梯隊為平滑基準率、L2 logistic、梯度提升；模型走 expanding
walk-forward，保留 purged gap，校準方法在獨立留出段選擇，再在最終留出段計分。
LLM 只能做抽取或敘述，forecast KPI 路徑只允許 `none` 或
`narration_only`。

只有同時符合下列條件才會保存並顯示數字：

- 時間外 Brier Skill 的 90% bootstrap 區間下界大於 0；
- 當次機率區間總寬不超過 0.40；
- 正／負控制通過。

未過閘時 `probability`、`lower_bound`、`upper_bound` 一律為
`null`；UI 與 CLI 只顯示「資料不足」。

## Quant adapter

Adapter 只開啟檔案讀取，並檢查：

- path 必須留在設定的 Quant 根目錄；
- JSON object、schema version 型別、SHA-256；
- `as_of/observed_at/fetched_at` 與 freshness；
- missing/stale `latest` pointer；
- point-in-time、leakage check、LLM involvement、orders-generated 旗標；
- 價格結算只選不晚於目標日的最後有效 bar。

公司頁目前讀取價格、SEC 基本面、factor、validation、conformal、
forward context、deep dive 與 ticker solver artifact。任一關鍵 artifact 缺失或違反
PIT 會明確降級 evidence grade。

## 本機 API

主要路徑：

- `/api/narrative/imports`、`/claims/{id}/review`
- `/api/narrative/discovery`、`/contracts`、`/forecasts`
- `/api/narrative/resolutions`、`/sources`
- `/api/narrative/dashboard`、`/company/{ticker}`、`/history`
- `/api/narrative/board/{ticker}?horizon=1y`（結果優先的局面工作區）
- `/api/narrative/calibration`
- `/api/narrative/research/themes`、`/packs`、`/packs/{id}/diff`
- `/api/narrative/research/runs`、`/companies/{ticker}`、`/graphs/{run_id}`
- `/api/narrative/research/graphs/edges/{edge_id}/review`（禁止 proposed 直接跳 verified）
- `/api/narrative/research/relationships`、`/bottlenecks`、`/coverage`
- `/api/narrative/research/bottlenecks/{id}/review`（observed 需兩個 A/B 維度）
- `/api/narrative/research/live`、`/monitor`、`/stress-tests`
- `/api/narrative/research/official/sec`、`/official/federal-register`
- `/api/narrative/research/official/congress`、`/official/regulations`（只在 POST 後取得）

探索、forecast 與 recalibration 使用 Radar `JobManager`；狀態由
`/api/jobs/{id}` 查詢，SSE 日誌在 `/api/jobs/{id}/log`。
服務只由 `radar-ui` 綁定 `127.0.0.1`。
