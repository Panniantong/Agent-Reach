# Karpathy 方法論知識庫

> 種子蒸餾 2026-07-09 · 來源：karpathy/autoresearch、karpathy/nanochat 公開 README 與設計
> 用 `agent-reach radar-backfill --handle karpathy --repos karpathy/autoresearch,karpathy/nanochat --distill`
> 重新蒸餾（含歷史 X posts 全量），人工審核後更新本檔。

## 核心原則（自動迭代）

1. **固定評測是一切的地基**。autoresearch 的整夜自主實驗之所以可行，是因為 val_bpb
   是一個不可被 agent 動搖的客觀指標——沒有固定指標的「自我改進」只是漂移。
2. **三檔分離**：`prepare.py`（固定的 harness 與評測，agent 永不碰）、`train.py`
   （agent 自由修改的實驗對象）、`program.md`（只有人類編輯的目標與規則）。
   權限邊界寫進架構，而不是寫進提示詞。
3. **短實驗預算**：每個實驗固定 5 分鐘牆鐘時間 → 一小時 12 次迭代。快速廉價的
   實驗迴圈勝過完美的單次實驗；迭代速度本身就是能力。
4. **保留/丟棄是二元決策**：跑完實驗、對比指標、keep or discard，全部寫進 log。
   不做「感覺變好了」的模糊判斷。
5. **單一複雜度旋鈕**：nanochat 用 `--depth` 一個參數帶動全部超參數推導。
   可調的東西越少，實驗結論越乾淨。
6. **最小可跑全鏈路**（speedrun 哲學）：先讓 tokenizer→pretrain→SFT→RL→inference
   端到端跑通、有分數上榜，再談優化。全鏈路的爛分數勝過半鏈路的好分數。

## 精要規則

- 改動前先定義「怎麼算更好」；沒有指標的改動不做。
- 一次實驗只動一個變因；動了什麼、分數差多少，一行 log 說清楚。
- 實驗預算固定且短；超時即失敗。
- 評測集凍結；誰都不准為了分數去改評測。
- 丟棄是常態，保留是例外；回滾必須是零成本操作。
- 系統複雜度用一個旋鈕表達；其他參數由它推導。
- 端到端先跑通，再局部優化。

## 實驗設計模式

| 概念 | autoresearch 做法 | 本 repo（radar_evolve）對映 |
|---|---|---|
| 固定評測 | 凍結資料上的 val_bpb | 凍結 heldout 材料上的主師 rubric 均分 |
| 實驗對象 | train.py | evolve/radar.yaml、radar.py、radar_report.py prompts、radar_arxiv.py |
| 人類編輯區 | program.md | evolve/program.md |
| 實驗預算 | 5 分鐘牆鐘 | --budget N 次實驗 + subprocess timeout |
| 決策 | keep if val_bpb 改善 | keep if rubric_mean >= base + epsilon |
| 記錄 | 實驗 log | evolve/journal.jsonl + journal.md |

## 原始出處索引

- https://github.com/karpathy/autoresearch — prepare.py / train.py / program.md 三檔架構、
  5 分鐘實驗預算、val_bpb 指標、overnight agent 迴圈（90k+ stars）
- https://github.com/karpathy/nanochat — $100 全鏈路 ChatGPT（tokenizer→pretrain→SFT→RL→
  inference）、`--depth` 單旋鈕、Time-to-GPT-2 speedrun 排行榜
- @karpathy X 歷史 posts：待 `radar-backfill` 全量抓取後補充蒸餾
