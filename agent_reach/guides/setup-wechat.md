# 微信公众号配置指南

## 功能说明
读取微信公众号文章。需要 Playwright 来处理微信的反爬机制。

## Agent 可自动完成的步骤

1. 检查 Playwright 是否安装：
```bash
python3 -c "import playwright; print('installed')" 2>&1
```

2. 安装 Playwright + 浏览器：
```bash
pip install playwright
playwright install chromium
```

3. 安装完成后测试：
```bash
curl -s "https://r.jina.ai/https://mp.weixin.qq.com/s/一个测试链接" -H "Accept: text/markdown"
```

## 需要用户手动做的步骤

请告诉用户：

> 微信公众号的配置很简单，只需要安装一个浏览器组件（约 150MB）。
>
> 我来帮你安装，你不需要做任何事情。安装过程大约 1-2 分钟。
>
> 安装好之后就可以直接读取微信公众号文章了，不需要登录。

## Agent 操作流程

1. 安装 Playwright：`pip install playwright`
2. 安装 Chromium：`playwright install chromium`
3. 测试：读一篇微信文章
4. 反馈："✅ 微信公众号已配置！发给我任何公众号文章链接，我都能读取。"
5. 如果安装失败（空间不足等）："❌ 浏览器组件安装失败。可能是磁盘空间不足（需要约 150MB）。"
