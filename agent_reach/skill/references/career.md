# 职场招聘

LinkedIn、Boss直聘。

## LinkedIn

```bash
# 获取个人资料
mcporter call linkedin.get_person_profile linkedin_username="username" sections="experience,education"

# 搜索人才
mcporter call linkedin.search_people keywords="AI engineer" location="Shanghai"

# 获取公司资料
mcporter call linkedin.get_company_profile company_name="openai" sections="posts,jobs"

# 搜索职位
mcporter call linkedin.search_jobs keywords="software engineer" location="Remote" max_pages=2
```

> **需要登录**: 首次使用前运行 `uvx mcp-server-linkedin@latest --login`，保存有效登录态。

### Fallback 方案

如果 MCP 不可用，可以用 Jina Reader：

```bash
curl -s "https://r.jina.ai/https://linkedin.com/in/username"
```

## Boss直聘

当用户说“帮我配 Boss直聘”时，按本节完成安装、启动专用 Chrome、等待用户手动
登录和最终验证。不要把 9222 端口等实现细节先甩给用户，也不要替用户输入账号、
扫码或处理滑块。

> **依赖状态**：所需公开 strict-CDP API 在 boss-agent-cli PR #382 中，尚未发布。
> Agent Reach 的临时安装器锁定 fork 提交
> `ba0f12541079ad794eae4c3bf3fc348befd228c9`，而不是会移动的 branch；上游发布后
> 应把安装器切回正式版本约束。

体检（无副作用，不搜索）：

```bash
agent-reach doctor          # boss 行：off = 未装或 CDP 不通；warn = 链路就绪
```

搜索 + JD 使用公开 API（`browser_mode` / `job_card_browser` / `JobItem.lid`）。
因为 pipx/uv tool 是隔离环境，普通 `python` 不一定能 import 已安装工具；临时阶段
用 `uv run --with` 保证脚本和锁定依赖处于同一解释器环境：

```bash
uv run --isolated --no-project \
  --with 'git+https://github.com/iqjiy/boss-agent-cli.git@ba0f12541079ad794eae4c3bf3fc348befd228c9' \
  python - <<'PY'
from pathlib import Path

from boss_agent_cli.api.client import AccountRiskError, BossClient, EnvironmentRiskError
from boss_agent_cli.auth.manager import AuthManager
from boss_agent_cli.platforms.zhipin import BossPlatform

auth = AuthManager(Path.home() / ".boss-agent")

# 严格 CDP 模式：跳过 Bridge、CDP 失败立即抛错、永不 headless
with BossClient(
    auth,
    cdp_url="http://localhost:9222",
    browser_mode="cdp_required",
) as boss:
    raw = boss.search_jobs("大模型", city="深圳", page=1)
    if raw.get("code") != 0:
        code, message = BossPlatform(boss).parse_error(raw)
        raise RuntimeError(f"{code}: {message}")
    items = raw.get("zpData", {}).get("jobList", [])
    for item in items:
        card = boss.job_card_browser(item["securityId"], item["lid"])
        post_desc = card.get("zpData", {}).get("jobCard", {}).get(
            "postDescription", ""
        )
        print(item.get("jobName"), post_desc)

# AccountRiskError / EnvironmentRiskError → 立即停止，不自动重试；
# 明确 token/stoken 过期的 code 37 由 BossClient 最多刷新并重试一次。
PY
```

### 环境体检与恢复（抓取前必查）

搜索前若 `agent-reach doctor` 报 boss 为 `off` 或 `warn`，按下面 runbook 排查，不要读源码瞎猜：

1. **CDP 端口通不通**：
   ```bash
   curl -s http://localhost:9222/json/version   # 有 Browser 字段 = 端口通
   ```

2. **调试 Chrome 没开 / 已关**：按系统启动专用 Chrome（登录态独立，不污染日常浏览器）：
   ```bash
   # macOS
   open -na "Google Chrome" --args --remote-debugging-address=127.0.0.1 \
     --remote-debugging-port=9222 --user-data-dir="$HOME/.boss-chrome-profile" \
     "https://www.zhipin.com/web/geek/job"

   # Linux
   google-chrome --remote-debugging-address=127.0.0.1 \
     --remote-debugging-port=9222 --user-data-dir="$HOME/.boss-chrome-profile" \
     "https://www.zhipin.com/web/geek/job"
   ```

   Windows PowerShell：
   ```powershell
   Start-Process chrome.exe -ArgumentList '--remote-debugging-address=127.0.0.1','--remote-debugging-port=9222',"--user-data-dir=$env:USERPROFILE\.boss-chrome-profile",'https://www.zhipin.com/web/geek/job'
   ```

   只绑定回环地址。任何能访问 9222 的进程都能完全控制该 Chrome；不要监听公网。
   这个专用 profile 要长期复用，以保留稳定登录态；不要每次运行时删除或新建，
   也不要默认切换到日常主 Chrome。不使用时关闭这个专用窗口。

3. **用户手动登录**：暂停并让用户在这个专用窗口登录、扫码或处理滑块。用户确认
   完成后，保存 CDP 登录态：
   ```bash
   boss --cdp-url http://localhost:9222 login --cdp
   ```

4. **登录态是否有效**（stoken 是否过期）：
   ```bash
   boss status
   agent-reach doctor
   ```

5. **错误码处置**（搜索/取 JD 时）：
   - code 36（ACCOUNT_RISK）→ 立即停，手动到 BOSS 页面处理，不可自动重试；
   - code 9（RATE_LIMITED）→ 冷却后重试；
   - code 37 + `环境存在异常` → `ENVIRONMENT_RISK`，立即停止，不刷新 Token、不重新登录、不自动重试；
   - 只有文案明确表示 token/stoken 过期的 code 37 才是 `TOKEN_REFRESH_FAILED`；客户端最多自动刷新并重试一次，仍失败再重新登录。

用户要求开始搜索时，Agent 必须指定严格 CDP 模式：

```bash
boss --browser-mode cdp-required --cdp-url http://localhost:9222 search "大模型" --city 广州 --page 1
```

不要无提示连续翻页。boss-agent-cli PR #383 为跨 CLI 进程的普通搜索增加持久
5–10 秒列表预算；该 PR 合并发布前，Agent 仍应主动串行、降频调用。
