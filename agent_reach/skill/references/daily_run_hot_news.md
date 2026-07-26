# Daily-run 热点新闻（60s API 自建）

daily-run 宏观采集会从 [60s API](https://github.com/vikiboss/60s) 拉取多平台热搜与「每天 60 秒读懂世界」要闻，并匹配持仓/板块关键词。

## 一键自建（推荐，无需 Docker）

**依赖：** Node.js **22.6+**、git、npm（本机进程监听 `127.0.0.1:8787`）

默认 **Web 面板**：`http://127.0.0.1:8786`（可读 HTML；默认监听 `0.0.0.0`，局域网可用 `http://<本机IP>:8786`）  
API 后端：`http://127.0.0.1:8787`（根路径 `/` 返回 JSON 元数据，属正常行为）  
Web 面板会通过同源 `/v2/*` 代理 API，手机/其他电脑打开面板时无需直连 8787。

```bash
# 完整 bootstrap（含 portfolio + mcporter + 60s + Web 面板）
bash scripts/daily-run-local-setup.sh

# 仅部署 60s + Web 面板
bash scripts/60s-local-setup.sh
# 或
python3 -m agent_reach.cli daily-run hot-news install
```

源码 clone 到 `~/.agent-reach/vendor/60s-api/`，日志 `~/.agent-reach/daily_run/logs/60s.log`，PID `~/.agent-reach/daily_run/60s.pid`。
Web 面板日志：`~/.agent-reach/daily_run/logs/60s_portal.log`

## 重启自启

`daily-run hot-news install` 默认会写入用户 crontab 的 `@reboot` 条目（延迟 30s 启动 60s + Web 面板）。

```bash
# 单独安装 @reboot 自启
python3 -m agent_reach.cli daily-run hot-news install-reboot

# 查看 @reboot 配置
python3 -m agent_reach.cli daily-run hot-news print-reboot-cron

# 安装 60s 但不写 @reboot
python3 -m agent_reach.cli daily-run hot-news install --no-reboot-cron
```

日志：`~/.agent-reach/daily_run/logs/60s-reboot-YYYY-MM-DD.log`

## 常用命令

```bash
# 查看本地 60s / 公共 fallback 状态
python3 -m agent_reach.cli daily-run hot-news status

# 强制重建（重新 clone + npm install + 启动）
python3 -m agent_reach.cli daily-run hot-news install --force

# 停止本机进程
python3 -m agent_reach.cli daily-run hot-news stop

# 停止并删除 vendor 源码目录
python3 -m agent_reach.cli daily-run hot-news stop --remove
```

## 部署模式

| 模式 | 命令 | 说明 |
|------|------|------|
| **native**（默认） | `install` 或 `install --mode native` | Node.js 本机进程，无需 Docker |
| docker | `install --mode docker` | Docker 容器 `vikiboss/60s` |
| auto | `install --mode auto` | 先 native，失败再 docker |

## 配置

安装后写入 `~/.agent-reach/daily_run_settings.json`：

```json
"hot_news": {
  "enabled": true,
  "base_urls": ["http://127.0.0.1:8787", "https://60s.viki.moe"],
  "platforms": ["60s", "weibo", "zhihu", "it-news"],
  "deploy": { "mode": "native" }
}
```

- 优先本地 `127.0.0.1:8787`；不可达时自动 fallback 到公共实例
- 缓存目录：`~/.agent-reach/daily_run/cache/hot_news_*.json`

## 验证

```bash
curl -sf 'http://127.0.0.1:8787/v2/60s?encoding=json' | head
python3 -m agent_reach.cli daily-run hot-news status
```

完整 daily-run 文档见仓库 `agent_reach/skill/daily_run_skill.md`。
