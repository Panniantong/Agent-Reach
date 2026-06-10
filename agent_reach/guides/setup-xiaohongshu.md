# 小红书配置指南

## 功能说明
读取和搜索小红书笔记。通过 [xhs-cli](https://github.com/jackwener/xiaohongshu-cli)（⭐1.5K，pipx 一行安装）实现。

## 前置条件
- Python 3.10+（pipx 安装）
- 浏览器已登录 xiaohongshu.com（用于导出 Cookie）

## Agent 可自动完成的步骤

### 1. 安装 xhs-cli
```bash
pipx install xiaohongshu-cli
```

### 2. 登录（从浏览器提取 Cookie）
```bash
xhs login
```

> 这会自动从浏览器提取 Cookie。如果自动提取失败，可以手动导入（见下方）。

### 3. 验证
```bash
agent-reach doctor
```

应该看到小红书显示为 ✅。

## 需要用户手动做的步骤

如果 `xhs login` 自动提取失败，需要手动导入 cookies：

> **推荐方式：Cookie-Editor 浏览器导出（最可靠）**
>
> 1. 在 Chrome 中安装 [Cookie-Editor](https://chromewebstore.google.com/detail/cookie-editor/hlkenndednhfkekhgcdicdfddnkalmdm) 扩展
> 2. 浏览器登录 xiaohongshu.com
> 3. 点击 Cookie-Editor 图标 → Export → Header String
> 4. 把导出的字符串发给 Agent，运行：`agent-reach configure xhs-cookies "导出的cookie字符串"`
>
> **注意**：不要依赖 QR 扫码登录，Cookie-Editor 导出方式最简单可靠。

## 使用示例

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
A: 重新运行 `xhs login` 或通过 Cookie-Editor 重新导出。

**Q: 小红书提示 IP 风险？**
A: 推荐使用住宅代理：`export HTTP_PROXY="http://user:pass@ip:port"`。

**Q: xhs-cli 不支持我的系统？**
A: 确保 Python 3.10+ 和 pipx 已安装。运行 `pipx install xiaohongshu-cli` 即可。

## 备选方案：Docker MCP

如果你已经在使用 [xiaohongshu-mcp](https://github.com/xpzouying/xiaohongshu-mcp) Docker 方案，它也能正常工作：

```bash
docker run -d \
  --name xiaohongshu-mcp \
  -p 18060:18060 \
  xpzouying/xiaohongshu-mcp

mcporter config add xiaohongshu http://localhost:18060/mcp
```

xhs-cli 是当前推荐方案，不需要 Docker，安装更简单。
