# 会话配置 / Sessions

仅在安装、登录、导入或退出时加载。Load only for setup, login, import or logout.

## Cloak 默认运行模式 / Default mode

小红书、BOSS、Instagram、Facebook、Twitter、Reddit、LinkedIn 的 Cloak 查询和导入验收统一使用 `headless=True`，不弹出浏览器窗口，无需额外参数。`cloak login CHANNEL` 是显式可视登录入口，用户登录完成后关闭窗口保存会话。Cloak 登录和查询不需要 OpenCLI；已有浏览器登录态导入仅为可选迁移路径。

Cloak queries and import verification run headless by default for XHS, BOSS and Instagram. No extra flag is needed. Use `cloak login CHANNEL` for independent visible login, then close the window to save. Existing Chrome cookie import is optional.

## 先检查 / Inspect first

`agent-reach login CHANNEL` 默认只返回连接选项和历史验收，不执行登录。
Use `agent-reach check CHANNEL --search` for one bounded live search check. Saved state does not prove a current login.

统一入口是 `agent-reach ensure CHANNEL` 或 MCP `reach_ensure`。它负责依赖、会话来源与正式验收；带 `--reuse-profile ID` 时才保存该站点的浏览器导入授权。需要本人登录或验证时，查询返回 `operation_id`，完成后运行 `agent-reach resume OPERATION_ID` 或 MCP `reach_resume`。`ensure CHANNEL --forget-source` 撤销导入授权。

`setup` installs default channels. XHS and BOSS are optional: `agent-reach add xiaohongshu` or `agent-reach add boss` installs Cloak SDK and its browser binary without opening a browser. Installation does not import credentials.

窗口生命周期：`cloak login CHANNEL` 打开一次可视 Cloak 窗口。用户完成登录后关闭该窗口，Reach 才保存会话；15 分钟内未关闭则超时并结束该窗口，不要自动重试。Cloak 查询和导入验收是 headless，执行结束会关闭自己的上下文。`browser setup` 属于旧的专用 OpenCLI Chrome 路径，可能显示 `OpenCLI Browser` 和 `about:blank`；它闲置约 10 分钟后关闭。通过 `browser use ID` 复用用户 Chrome 时，Reach 不关闭用户窗口。若同时出现两种窗口，先查实际执行的命令，不要把 OpenCLI Browser 称为 Ego Lite。

## Cloak：小红书与 BOSS / XHS and BOSS

独立路径：运行 `agent-reach cloak login CHANNEL`，用户登录完成后关闭窗口；再用 `--backend cloakbrowser` 验收查询。关闭窗口只标记会话已保存，不声称登录或业务验收成功。窗口等待上限 15 分钟；关闭登录窗口后再执行查询。

可选导入路径：

1. 用户明确授权后，选择已有会话。已有授权不必重复询问。
2. `agent-reach browser profiles` 列出连接；不要猜账号。
3. `agent-reach cloak import CHANNEL --opencli-profile ID` 仅导入该站 Cookie，并创建独立 headless Profile。另一入口是 `--state-file FILE`，仅使用用户指定的本地文件。
4. 导入会执行搜索验收；失败时依据错误码停止或修复，不反复切换账号。

Explicit authorization is required before importing site cookies into an independent profile. Never print credentials. Import copies cookies only, not the complete browser identity, localStorage or IndexedDB. `cloak status CHANNEL` reports local setup, not live authentication.

`--backend opencli` selects the existing Chrome session. BOSS search also supports `--backend boss-agent-cli` with an explicitly bound CDP browser. BOSS read currently supports only Cloak; do not promise OpenCLI detail fallback.

退出 Cloak 使用 `agent-reach logout CHANNEL` 或 `agent-reach cloak logout CHANNEL`。它只删除 Reach 管理的该站独立 Profile，不注销原浏览器。

## OpenCLI

Use `agent-reach browser use ID --label NAME` to select the shared existing browser, or `agent-reach browser bind CHANNEL ID` for an override. If disconnected, reconnect the extension in that browser. Do not silently open another profile.

OpenCLI 的普通 logout 不删除 Chrome Cookie；真正退出网站需用户在原浏览器操作。解除绑定使用 `agent-reach browser unbind CHANNEL`。

## 原生工具 / Native tools

LinkedIn jobs 优先 Cloak，原有 linkedin-mcp 是后备；B站复用工具已有配置。仅在需要时显式执行 `agent-reach login CHANNEL --native`；该工具可能打开浏览器或二维码。`--import-existing` 仅用于用户明确要求导入已有工具状态。普通 Chrome 登录态不能直接视为 MCP 登录态。

For native BOSS CDP, inspect `agent-reach login boss` first. Bind an existing CDP endpoint explicitly; ordinary Chrome without CDP is not attachable through CDP. Only `login boss --new-browser` explicitly opens a dedicated browser. The user confirms login and page stability before sync/search.

## Instagram

Instagram 的 search/profile/posts 使用 CloakBrowser → OpenCLI。各渠道仍需在目标机器上实测。

`agent-reach add instagram` 安装主后端，`agent-reach cloak login instagram` 提供独立登录。可选迁移方式：用户明确授权后，通过 `agent-reach cloak import instagram --opencli-profile ID` 或 `--state-file FILE` 导入站点 Cookie，再运行 `agent-reach check instagram --search`。

search 搜索用户；profile 读取主页信息；posts 返回指定用户的帖子描述。图片和视频内容不在当前读取范围内。

Instagram search/profile/posts use CloakBrowser first, OpenCLI second. Import and logout follow the Cloak steps above. Search returns users; posts return captions.

Facebook search 已接入 CloakBrowser → OpenCLI；profile 仍使用 OpenCLI。可用 `cloak login facebook` 独立登录，或显式 `cloak import facebook --opencli-profile ID` 迁移站点 Cookie。
