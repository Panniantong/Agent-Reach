# 小红书配置指南

## 功能说明
读取和搜索小红书笔记。桌面优先使用 OpenCLI，服务器使用
[xiaohongshu-mcp](https://github.com/xpzouying/xiaohongshu-mcp)；
xhs-cli 仅作为已安装用户的存量备选。

## 前置条件
- OpenCLI：用户已经存在且明确控制的 Chrome 小红书会话
- xiaohongshu-mcp / 存量工具：Cookie-Editor 浏览器扩展

## 认证边界

Agent Reach 不替用户执行小红书登录，也不读取浏览器 Cookie。

OpenCLI 只使用用户已经存在且明确控制的 Chrome 会话。
`agent-reach configure xhs-cookies` 不会把 Cookie 注入 OpenCLI 或 Chrome。
如果没有现成会话，不要自动登录；改用 Cookie-Editor 手工导出后配置
xiaohongshu-mcp 或存量工具：

1. 在 Chrome 中安装 [Cookie-Editor](https://chromewebstore.google.com/detail/cookie-editor/hlkenndednhfkekhgcdicdfddnkalmdm) 扩展
2. 用户自行在 xiaohongshu.com 准备要导出的会话
3. 点击 Cookie-Editor 图标 → Export → Header String
4. 把导出的字符串发给 Agent，运行：

```bash
agent-reach configure xhs-cookies "导出的 Cookie Header String"
agent-reach doctor
```

该显式命令会保存/导入用户提供的 xiaohongshu.com 同域 Cookie 集；执行前请
确认 Cookie 名称和范围。非 xiaohongshu.com 域 Cookie 会被忽略。

如果 xiaohongshu-mcp 容器正在运行，配置命令会把 Cookie 导入容器；否则会写入
owner-only 的本地文件，并打印后续手工导入路径。

## 使用示例

先按 `agent-reach doctor --json` 的 `active_backend` 选择命令。存量 xhs-cli 示例：

搜索笔记：
```bash
xhs search "关键词"
```

阅读笔记详情：
```bash
xhs read NOTE_ID
```

查看评论：
```bash
xhs comments NOTE_ID
```

## 常见问题

**Q: Cookie 过期了？**
A: 重新通过 Cookie-Editor 手工导出，再运行
`agent-reach configure xhs-cookies "新的 Cookie Header String"`。

**Q: 小红书提示 IP 风险？**
A: 推荐使用住宅代理：`export HTTP_PROXY="http://user:pass@ip:port"`。

**Q: xhs-cli 不支持我的系统？**
A: 确保 Python 3.10+ 和 pipx 已安装。运行 `pipx install xiaohongshu-cli` 即可。

## 服务器方案：Docker MCP

如果你已经在使用 [xiaohongshu-mcp](https://github.com/xpzouying/xiaohongshu-mcp) Docker 方案，它也能正常工作：

```bash
docker run -d \
  --name xiaohongshu-mcp \
  -p 18060:18060 \
  xpzouying/xiaohongshu-mcp

mcporter config add xiaohongshu http://localhost:18060/mcp --scope home
```

该服务器后端使用上面的 Cookie-Editor 手工导出流程。
