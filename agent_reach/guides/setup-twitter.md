# Twitter 高级功能配置指南（bird CLI）

## 功能说明
基础 Twitter 功能（搜索+读单条推文）无需配置，开箱即用。

高级功能需要 bird CLI：
- 查看用户时间线
- 深度搜索（更精确、更多结果）
- 读取完整线程（thread）
- 查看关注列表推文

bird 是免费开源工具（npm 包 @steipete/bird），但需要你的 Twitter 账号 cookie。

## Agent 可自动完成的步骤

1. 检查 bird 是否安装：
```bash
which bird && echo "installed" || echo "not installed"
```

2. 安装 bird：
```bash
npm install -g @steipete/bird
```

3. 测试（需要先配置 cookie）：
```bash
AUTH_TOKEN="xxx" CT0="yyy" bird search "test" -n 1
```

4. 用 agent-reach 配置 cookie（推荐）：
```bash
agent-reach configure twitter-cookies "auth_token=xxx; ct0=yyy"
```

## 需要用户手动做的步骤

请告诉用户：

> Twitter 高级功能需要你的 Twitter 账号 cookie（完全免费）。
>
> **最简单的方式：**
> 1. 安装 Chrome 插件 [Cookie-Editor](https://chromewebstore.google.com/detail/cookie-editor/hlkenndednhfkekhgcdicdfddnkalmdm)
> 2. 打开 https://x.com 并确保已登录
> 3. 点击 Cookie-Editor 插件图标 → Export → Header String
> 4. 把导出的内容发给我
>
> **手动方式：**
> 1. 用 Chrome 打开 https://x.com 并确保你已登录
> 2. 按 **F12** 打开开发者工具（Mac 按 Cmd+Option+I）
> 3. 点击顶部的 **Application**（应用）标签
> 4. 左侧找到 **Cookies** → **https://x.com**
> 5. 在列表中找到以下两个值，双击复制：
>    - **auth_token** — 一串字母数字
>    - **ct0** — 一串字母数字
> 6. 把这两个值发给我
>
> ⚠️ 这些 cookie 让我能以你的身份读取推文（只读）。我不会发推、点赞或做任何操作。
> ⚠️ cookie 大约 1-3 个月会过期，届时需要重新导出。

## Agent 收到 cookie 后的操作

1. 安装 bird（如果没装）：`npm install -g @steipete/bird`
2. 配置 cookie：`agent-reach configure twitter-cookies "粘贴的内容"`
3. 测试：运行 `agent-reach doctor` 确认 Twitter 状态
4. 反馈："✅ Twitter 高级功能已开启！现在可以搜索推文、查看时间线了。"
5. 如果失败："❌ Cookie 无效或已过期，请重新导出。"
