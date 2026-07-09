# Radar Evolve — Program（只有人類可以編輯本檔）

## 目標

提升每日簡報的**凍結評測分數**：pinned 學生在凍結 heldout 材料上起草、
凍結 rubric（coverage / accuracy / depth / lens_application / actionability）
評分的平均 total。目前的槓桿按影響力排序：

1. `agent_reach/radar_report.py` 的 **STUDENT_SYSTEM**、**STRUCTURE_TEMPLATE**
   與 `student_draft` 的 user prompt 組裝——這是唯一直接影響凍結評測的路徑
   （材料已凍結，收集器配置動不了它）。
2. `agent_reach/radar.py` / `agent_reach/radar_arxiv.py` 的收集與排序邏輯、
   `evolve/radar.yaml` 的關鍵字與權重——**不影響凍結評測**，只在通過
   health gate 的前提下做維護性改進；除非 program 明確要求，優先級最低。

## 硬規則（違反 = 直接丟棄）

- 一次實驗只改**一個檔案、一件事**（單一變因）。
- 不得動 tests/、evolve/fixtures/、本檔、radar_evolve.py（manifest 哈希會抓）。
- 改 code 必須保持既有函數簽名（health gate + pytest 會驗）。
- 學生 prompt 的「防照抄鐵律」與「繁體中文輸出」條款不得刪除或弱化。
- 不要重試日誌裡已被丟棄的假設。

## 假設 backlog（人類補充，agent 依序考慮）

- 學生常把觀點寫成事實：強化 [事實]/[觀點] 標註的 few-shot 說明（無事實內容）。
- 「怎麼讀」透鏡的反向解讀常被忽略：在 STUDENT_SYSTEM 把透鏡規則提到最前面。
- 個股彙總表常漏材料中的代號：在 user prompt 結尾加一步自查清單。

## 預算

- 預設每晚 `--budget 5`，epsilon = 1.0（分數要贏過 base + 1 才保留）。
- 覺得失控：`touch evolve/STOP`（下一輪立即停）。
