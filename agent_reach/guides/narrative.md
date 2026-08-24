# 敘事推演與校準機率

`radar-narrative` 把外部觀點拆成可覆核主張，再連到只讀 Quant artifact、事件契約、
時間外校準與追加式結算。它是研究工作台，不建立部位、訂單或交易指令。

## 安裝與資料位置

```bash
pip install "agent-reach[ui,narrative]"
agent-reach radar-ui
```

- 結構化資料：`~/.agent-reach/radar/narrative/narrative.sqlite3`
- 不可變原文：`~/.agent-reach/radar/narrative/blobs/<sha256>.<ext>`
- Quant 根目錄：預設 `D:\DOT\Quant\data`，只讀
- 設定覆寫：`narrative_data_dir`、`quant_data_root`
- SQLite schema 由 `PRAGMA user_version` 管理；較新且不相容的 schema 會拒絕開啟

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
- `/api/narrative/calibration`

探索、forecast 與 recalibration 使用 Radar `JobManager`；狀態由
`/api/jobs/{id}` 查詢，SSE 日誌在 `/api/jobs/{id}/log`。
服務只由 `radar-ui` 綁定 `127.0.0.1`。
