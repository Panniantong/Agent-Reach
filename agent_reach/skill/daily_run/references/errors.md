# daily-run 错误与补跑

盘中/收盘/调度专用。通用平台错误见 [agent-reach errors.md](../../../agent-reach/references/errors.md)。

## schedule / lock

| 信号 | 动作 |
|------|------|
| `lockfile` / 任务正在运行 | 确认 PID 已退出 → 删 lock；补跑加 `--force` |
| manifest 去重 skip | `schedule run <job> --force` |
| 并行 intraday 无 `--force` | 会 skip；勿同时手工+cron |

## MSS / 调仓文案

| 现象 | 说明 |
|------|------|
| 卡片「进攻阈值 50」 vs harness 45 | 研判应读 **effective_settings**；见 `harness_display` 页脚 |
| 摩擦惩罚阻断 | 预期收益 ≤ 交易成本门槛；非 bug |
| MSS<macro_veto 仍显示「可做」 | 查 audit Gate；禁止强行买入 |

## Feishu

| 信号 | 动作 |
|------|------|
| `FeishuError` | `~/.agent-reach/config.env` + config.yaml |
| 主卡有、AI 卡无 | 查 manifest `narrative_feishu`；`llm_narrative` 是否 disabled |

## 工具门禁（Exa / 60s）

- Exa：同 query **86400s** 内不重复（`exa_cache`）
- 60s：`http://127.0.0.1:8787` → fallback `https://60s.viki.moe`
- 盘中 intraday：**不**拉 Exa 全量；仅 quotes enrich

## 补跑命令

```bash
REPO="${REPO:-$PWD}"
${REPO}/venv/bin/python3 -m agent_reach.cli daily-run schedule run intraday --force
```

日志：`~/.agent-reach/daily_run/logs/cron-YYYY-MM-DD.log`
