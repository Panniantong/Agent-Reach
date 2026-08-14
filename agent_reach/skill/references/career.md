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

> **状态**：channel 已注册，`agent-reach doctor` 会体检 CDP 链路（boss-agent-cli
> 装没装 → 9222 端口通不通 → 有无 zhipin 页签）。

体检（无副作用，不搜索）：

```bash
agent-reach doctor          # boss 行：off = 未装或 CDP 不通；warn = 链路就绪
```

搜索 + JD（公开 API，`browser_mode` / `job_card_browser` / `JobItem.lid`）：

```python
from boss_agent_cli.api.client import AccountRiskError, BossClient
from boss_agent_cli.auth.manager import AuthManager

# 严格 CDP 模式：跳过 Bridge、CDP 失败立即抛错、永不 headless
client = BossClient(auth, cdp_url="http://localhost:9222", browser_mode="cdp_required")

# 搜索（公开方法，返回原始 jobList 含 lid/securityId/encryptJobId）
raw = client.search_jobs("大模型", city="深圳", job_type="实习", page=1)
items = raw.get("zpData", {}).get("jobList", [])

# 取 JD（公开 job_card_browser，强制 CDP 浏览器通道，绕过 httpx 优先）
for item in items:
    card = client.job_card_browser(item["securityId"], item["lid"])
    post_desc = card.get("zpData", {}).get("jobCard", {}).get("postDescription", "")

# code 36（AccountRiskError）→ 立即停不可重试；code 9（RATE_LIMITED）→ 冷却重试；
# code 37（TOKEN_REFRESH_FAILED）→ 重新登录
```

> 上述接口尚未合入上游 boss-agent-cli（见 PR #382），本地开发用 fork 分支即可。

### 环境体检与恢复（抓取前必查）

搜索前若 `agent-reach doctor` 报 boss 为 `off` 或 `warn`，按下面 runbook 排查，不要读源码瞎猜：

1. **CDP 端口通不通**：
   ```bash
   curl -s http://localhost:9222/json/version   # 有 Browser 字段 = 端口通
   ```

2. **调试 Chrome 没开 / 已关**：重启专用 Chrome（登录态独立，不污染日常浏览器）：
   ```bash
   Google Chrome --remote-debugging-port=9222 \
     --user-data-dir=~/.boss-chrome-profile &
   ```

3. **必须有一个已打开的 zhipin 页签**（否则首次搜索会因导航竞态失败）：
   ```bash
   curl -s -X PUT "http://localhost:9222/json/new?https://www.zhipin.com/web/geek/job"
   ```

4. **登录态是否有效**（stoken 是否过期）：
   ```bash
   boss status          # 看 auth 状态与 stoken 新鲜度；过期则 boss login
   ```

5. **错误码处置**（搜索/取 JD 时）：
   - code 36（ACCOUNT_RISK）→ 立即停，手动到 BOSS 页面处理，不可自动重试；
   - code 9（RATE_LIMITED）→ 冷却后重试；
   - code 37（TOKEN_REFRESH_FAILED）→ 重新登录 / 刷新 zhipin 页。
