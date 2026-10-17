# CloakBrowser 第一后端

小红书 search/read：cloakbrowser → opencli。
BOSS search：cloakbrowser → opencli → boss-agent-cli；read：cloakbrowser。
使用 `--backend NAME` 可显式选择，通用 `read URL` 也支持此参数。

```sh
agent-reach add xiaohongshu
agent-reach add boss
# 或只安装主后端：agent-reach cloak setup
agent-reach cloak login xiaohongshu
agent-reach cloak login boss
# 在各自窗口本人登录后关闭，再执行查询。OpenCLI 不参与此路径。
agent-reach xiaohongshu search VLA --limit 3 --timeout 60
agent-reach boss search 数据平台 --city 深圳 --limit 3 --timeout 60
agent-reach boss read 'https://www.zhipin.com/job_detail/JOB_ID.html' --timeout 60
agent-reach xiaohongshu search VLA --backend opencli
agent-reach boss search 数据平台 --city 深圳 --backend boss-agent-cli
```

## 登录边界

安装不会开浏览器。导入是显式授权动作：会打开独立 headless 浏览器、复制该站 Cookie、访问该站做搜索探针；源浏览器不被修改，不上传 Cookie 给第三方。不复制完整 Chrome Profile，也不迁移其他站点的身份。

可用 `cloak import CHANNEL --state-file FILE` 导入 Cookie 数组或 Playwright storage_state 的 cookies 部分。本版不迁移 localStorage/IndexedDB。导入文件应只在本地使用，权限 600。临时副本导入结束即删除。

每站 Profile 位于 `~/.agent-reach/sessions/CHANNEL-cloak/profile`。查询不重新注入 Cookie，不随机创建空身份。`cloak status CHANNEL` 仅说明配置存在，业务访问通过也不等于核实了账号身份。失效时使用 `cloak login CHANNEL` 重新登录，或选择显式导入。`cloak logout CHANNEL` 清理独立 Profile，源 Chrome 不受影响。

## 安装与执行

主后端使用私有 Python venv，SDK 初始安装版本 0.6.3；平台免费内核固定为该 SDK 声明的版本，运行时不下载或自动升级。macOS 验证版本为 Chromium 145.0.7632.109.2。OpenCLI 与原生 Boss 作为可选后端保留，已有安装不被替换；仅安装主后端不会自动装所有备用工具。

运行子进程执行固定的只读脚本，不接受任意 JavaScript。每个 Profile 独占锁，命令超时停止进程组；Windows 使用 `taskkill /PID /T /F` 清理本次命令的进程树，并为清理预留时间。Windows 已实测 headless 启动与超时子进程清理；站点登录与搜索仍须单独验收。

从 OpenCLI 导入时按 npm 包定位 `dist/src/browser/page.js`，同时兼容旧布局 `browser/page.js`。Windows 的 npm `.cmd` 启动器不能当作模块所在目录。导入前必须确认选中的 Bridge context 属于用户指定的已登录 Chrome Profile；空的临时浏览器不能作为登录来源。

NEED_LOGIN、PLATFORM_BLOCKED、RATE_LIMITED、BUSY 均终止回退。NEED_SETUP、UPSTREAM_BROKEN 在剩余时间足够时可以回退；共享总超时预算，不无限重试。`meta.attempts` 记录路径。普通用户只需知道执行成功或需要登录。

## 内容与能力上限

- 小红书只支持直接 www.xiaohongshu.com 的笔记链接，保留搜索返回的访问参数；不解析短链接。`raw.content_scope=description_only`，不包括图片 OCR 或视频转录。
- BOSS 支持常见城市名或 9 位城市码；未知城市不静默回退北京。
- BOSS 搜索卡片可能使用动态字体。无法直接读出时返回 `salary=null, salary_encoded=true`，不套用固定字符映射。详情里的可读薪资由 read 返回。
- 搜索是有上限的当前页面结果，并非全站穷尽；没有服务端薪资排序承诺。
- BOSS 的 OpenCLI detail 需要 security_id，尚未映射成统一 URL read，因此 read 只使用 CloakBrowser。

## 默认运行模式

小红书、BOSS、Instagram 的 Cloak 查询与导入验收统一使用 headless=True，无需额外参数。`cloak login CHANNEL` 单独提供可视登录入口，关闭窗口保存会话，登录与查询均不需要 OpenCLI。

Cloak 浏览器使用 Reach 已配置的 proxy；代理配置通过子进程环境传递。登录窗口最多等待 15 分钟；关闭后需另行验收查询。

Facebook search 已接入 CloakBrowser → OpenCLI；profile 仍使用 OpenCLI。可用 `cloak login facebook` 独立登录，或显式 `cloak import facebook --opencli-profile ID` 迁移站点 Cookie。

## 临时出网通道

`REACH_CLOAK_PROXY` 可为当前命令覆盖 Reach 保存的代理，配置值通过子进程环境传入浏览器，不写入站点会话或系统代理。Windows PowerShell 示例：

```powershell
$env:REACH_CLOAK_PROXY = 'http://127.0.0.1:17897'
agent-reach facebook search OpenAI --backend cloakbrowser --limit 3
Remove-Item Env:REACH_CLOAK_PROXY
```

该地址须有正在运行的代理或 SSH 转发。隧道关闭后会失去连通性；HTTP 200 仅证明网络访问，登录、搜索、限流和账号验证需分别验收。
