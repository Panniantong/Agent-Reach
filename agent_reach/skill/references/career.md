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

> **关键区分：登录门槛 ≠ 反爬安全校验。** zhipin.com 落地后可能停在三种页面：
> 已登录的 `web/geek/job`、未登录的 `web/user/`（扫码登录/手机号登录）、以及
> 反爬的**安全校验页**（URL 含 `security-check` / `zhipin-security` /
> `_security_check`）。安全校验页与登录无关：**已登录也会出现**（带 CDP 调试
> 端口的 Chrome 几乎必现）。绝不用当前页 URL 判断登录态。

> **双登录态存储（existing-browser 严格 CDP 模式下以浏览器为准）。** 存在两个凭据存储，
> **都不能删**，但认证的是不同通道：
>
> | 存储 | 角色 |
> |---|---|
> | `~/.boss-agent/auth/session.enc` | ① 硬性门槛：`_get_browser()` 无条件 `get_token()`，读不到直接 `AuthRequired`，CDP 搜索会在连浏览器前就失败；② **不是**搜索的认证凭据：CDP 复用真 Chrome 的 `contexts[0]` 时，它的 cookies 只在「无 context」分支注入，实际从未生效；③ httpx 通道（低危 op：`status`/`detail`/`cities`/`job_card_httpx`）真用它的 cookies + stoken，code 37 的 `force_refresh()` 也回写它 |
> | 专用 Chrome profile 内的浏览器 cookie | CDP 模式下 search/greet 等高危 op 实际携带的凭据 |
>
> **`boss status` / `status --live` 只校验 session.enc**——即使报
> `logged_in: true`，也不代表 CDP 浏览器已登录。所以：
> 1. 拉起专用 Chrome 后，第一步必须**暂停并让用户肉眼确认**窗口内是已登录
>    状态（右上角有头像），确认后才允许执行搜索；
> 2. doctor 的 boss 行会直接探测浏览器内有无 wt2 cookie，以它为准；
> 3. **`AUTH_EXPIRED` 是 ground truth**：搜索报它就直接走登录 runbook
>    （用户在专用窗口登录 → `login --cdp`），禁止再往「安全校验」方向解释；
>    `_security_check` 页面只在 `AUTH_EXPIRED` 不存在时才按滑块处理。
> 4. 不要为了「清理旧凭据」删除 session.enc；要刷新它就跑 `login --cdp`。

> **依赖状态**：所需公开 strict-CDP API 来自 boss-agent-cli 后继拆分 PR #403–#407
> （#402/#382 已按维护者意见拆分），已全部合并入上游 master。Agent Reach 的安装器锁定
> 上游固定提交
> `4c991b77086a203173bf08a4cb64a23af6514fe6`，而不是会移动的 branch；上游发布正式版后
> 应把安装器切回版本约束。

体检（无副作用，不搜索）：

```bash
agent-reach doctor          # boss 行：off = 未装或 CDP 不通；warn = 链路就绪，
                            # message 会注明浏览器内有无 wt2 登录 cookie（以浏览器为准）
```

搜索 + JD 使用公开 API（`browser_source` / `job_card_browser` / `JobItem.lid`）。
因为 pipx/uv tool 是隔离环境，普通 `python` 不一定能 import 已安装工具；
用 `uv run --with` 保证脚本和锁定依赖处于同一解释器环境：

```bash
uv run --isolated --no-project \
  --with 'git+https://github.com/can4hou6joeng4/boss-agent-cli.git@4c991b77086a203173bf08a4cb64a23af6514fe6' \
  python - <<'PY'
from pathlib import Path

from boss_agent_cli.api.client import AccountRiskError, BossClient, EnvironmentRiskError
from boss_agent_cli.auth.manager import AuthManager
from boss_agent_cli.platforms.zhipin import BossPlatform

auth = AuthManager(Path.home() / ".boss-agent")

# 严格 CDP 模式：复用已登录浏览器、CDP 失败立即抛错、永不 headless
with BossClient(
    auth,
    cdp_url="http://localhost:9222",
    browser_source="existing-browser",
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

   **拉起后第一步：暂停并让用户肉眼确认窗口内是已登录状态（右上角有头像）。**
   不要用 `boss status` 代替这一步——它只校验本地 session.enc，不代表浏览器。

3. **用户手动登录（浏览器未登录时）**：判定以 doctor 的浏览器 cookie 探测为准
   （无 wt2 = 浏览器未登录），其次才是用户肉眼确认；`boss status` 只作参考。
   让用户在这个专用窗口登录或扫码。用户确认完成后，保存 CDP 登录态：
   ```bash
   boss --cdp-url http://localhost:9222 login --cdp
   ```

   若窗口停在安全校验页（`security-check` / `zhipin-security`），这是反爬挑战、
   不是登录页：等它自动放行或让用户手动过一下滑块即可，不要当成“未登录”去
   重新扫码登录。

4. **登录态是否有效**（浏览器 cookie 探测 + stoken 是否过期）：
   ```bash
   agent-reach doctor     # 看 boss 行 message 里的浏览器 wt2 cookie 探测结果
   boss status            # 只反映本地 session.enc，仅作参考
   ```

5. **错误码处置**（搜索/取 JD 时）：
   - `AUTH_EXPIRED`（用户未登录）→ **ground truth**：CDP 浏览器未登录（不管
     `boss status` 说什么），直接走第 3 步登录流程 + `login --cdp`，禁止往
     「安全校验」方向解释；
   - code 36（ACCOUNT_RISK）→ 立即停，手动到 BOSS 页面处理，不可自动重试；
   - code 9（RATE_LIMITED）→ 冷却后重试；
   - code 37 + `环境存在异常` → `ENVIRONMENT_RISK`，立即停止，不刷新 Token、不重新登录、不自动重试；
   - 只有文案明确表示 token/stoken 过期的 code 37 才是 `TOKEN_REFRESH_FAILED`；客户端最多自动刷新并重试一次，仍失败再重新登录。

用户要求开始搜索时，Agent 必须指定严格 CDP 模式（全局选项放在子命令之前）：

```bash
boss --browser-source existing-browser --cdp-url http://localhost:9222 search "大模型" --city 广州 --page 1
```

不要无提示连续翻页。boss-agent-cli PR #383 为跨 CLI 进程的普通搜索增加持久
5–10 秒列表预算；该 PR 合并发布前，Agent 仍应主动串行、降频调用。

> **等待属预期，不是卡死**：连续搜索命中节流时，boss-agent-cli 会静默等待 5–10 秒
> （TTY 下会显示「节流等待 Ns…」提示；Agent Reach 以 `--json` 调用，看不到该提示）。
> 等待窗口内不要重试、不要拉起新浏览器、不要切换 profile。
