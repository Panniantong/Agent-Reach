# 社交媒体 & 社区

小红书、抖音、Twitter/X、微博、B站、V2EX、Reddit。

## 小红书 / XiaoHongShu (xhs-cli)

### 稳定可用的命令

```bash
# 搜索笔记（推荐入口）
xhs search "query"

# 阅读笔记详情（必须用搜索结果中的 URL 或 ID，不能裸 note_id）
xhs read NOTE_ID_OR_URL

# 查看评论
xhs comments NOTE_ID_OR_URL

# 浏览热门
xhs hot

# 推荐 feed
xhs feed
```

### 已知不稳定的命令（v0.6.4）

```bash
# 以下命令当前可能返回 API error，谨慎使用：
xhs user USER_ID          # 可能返回 {code: -1}
xhs user-posts USER_ID    # 可能返回 {code: -1}
xhs favorites              # 可能返回 API error
```

### 重要注意事项

> **安装**: `pipx install xiaohongshu-cli`，然后 `xhs login`（自动从浏览器提取 Cookie）。
>
> **xsec_token 限制**: 小红书强制 xsec_token 机制，**不能直接用裸 note_id 去读**。正确流程是：先 `xhs search` 或 `xhs feed` 获取结果，再用结果中的 URL/ID 去 `xhs read`。直接构造 note_id 会被拦截。
>
> **频率控制**: 高频请求（批量搜索、深翻评论）会触发验证码，这是平台限制无法绕过。建议每次操作间隔 2-3 秒。
>
> **POST 操作风险**: 发帖(post)、评论(comment)、点赞(like) 等写操作在 v0.6.x 可能因签名问题返回 406。如需使用，建议降级到 v0.3.5 (`pipx install xiaohongshu-cli==0.3.5`)。

## 抖音 / Douyin

### 安装与配置

`douyin-mcp-server` 是 **stdio 模式**的 MCP server，需先安装再注册到 mcporter：

```bash
# 1. 安装
pipx install douyin-mcp-server

# 2. 查找安装路径
pipx runpip douyin-mcp-server show -f 2>/dev/null | grep "Location" \
  || find ~/.local -name "douyin-mcp-server" 2>/dev/null | head -1

# 3. 注册到 mcporter（使用 stdio 模式，将路径替换为上一步的输出）
mcporter config add douyin --command "/path/to/douyin-mcp-server" --scope home
```

> **注意**：`agent-reach install --channels douyin` 暂不支持抖音渠道（抖音在"可选渠道待解锁"列表）。
> HTTP 模式（`mcporter config add douyin http://localhost:18070/mcp`）**无法正常工作**，请使用上方 stdio 方式。

### 用法

```bash
# 解析视频信息
mcporter call 'douyin.parse_douyin_video_info(share_link: "https://v.douyin.com/xxx/")'

# 获取无水印下载链接
mcporter call 'douyin.get_douyin_download_link(share_link: "https://v.douyin.com/xxx/")'

# 提取视频文案
mcporter call 'douyin.extract_douyin_text(share_link: "https://v.douyin.com/xxx/")'
```

> **无需登录**

## Twitter/X (twitter-cli)

### 稳定命令

```bash
# 首页时间线（最稳定）
twitter feed -n 20

# 读取单条推文（含回复）
twitter tweet URL_OR_ID

# 读取长文 / X Article
twitter article URL_OR_ID

# 用户时间线
twitter user-posts @username -n 20

# 用户资料
twitter user @username
```

### 可能不稳定的命令

```bash
# 搜索推文（Twitter 频繁改 GraphQL 端点，可能 404）
twitter search "query" -n 10
# 如果 search 返回 404，升级 twitter-cli：pipx upgrade twitter-cli

# likes（2024 年后只能看自己的，平台限制）
twitter likes
```

### 重要注意事项

> **安装**: `pipx install twitter-cli`（确保 v0.8.5+）
>
> **认证**: 推荐用 Cookie-Editor 导出后设置环境变量 `TWITTER_AUTH_TOKEN` + `TWITTER_CT0`。自动提取在 SSH/Docker/无头环境不可用。
>
> **IP 风控**: 不要在 VPS/数据中心 IP 上频繁调用，尤其是 followers/following，有封号风险。使用住宅代理或本地环境。
>
> **search 可能失效**: Twitter 频繁修改 GraphQL API，search 命令可能随时返回 404。如遇到，先 `pipx upgrade twitter-cli`。如果最新版仍不行，说明上游还没跟上 Twitter 的改动，用 `twitter feed` 替代。
>
> **输出格式**: 建议用 `--yaml` 或 `--json` 获得结构化输出，对 AI agent 更友好。

## 微博 / Weibo

```bash
# 使用 Jina Reader 读取
curl -s "https://r.jina.ai/https://weibo.com/USER_ID/POST_ID"
```

> 微博主要通过网页抓取，推荐使用通用网页读取方式。

## B站 / Bilibili

```bash
# 获取视频元数据
yt-dlp --dump-json "https://www.bilibili.com/video/BVxxx"

# 下载字幕
yt-dlp --write-sub --write-auto-sub --sub-lang "zh-Hans,zh,en" --convert-subs vtt --skip-download -o "/tmp/%(id)s" "URL"
```

> **注意**: 服务器 IP 可能遇到 412 错误。使用 `--cookies-from-browser chrome` 或配置代理。

## V2EX (公开 API)

无需认证，直接调用公开 API。

### 热门主题

```bash
curl -s "https://www.v2ex.com/api/topics/hot.json" -H "User-Agent: agent-reach/1.0"
```

### 节点主题

```bash
# node_name 如: python, tech, jobs, qna, programmers
curl -s "https://www.v2ex.com/api/topics/show.json?node_name=python&page=1" -H "User-Agent: agent-reach/1.0"
```

### 主题详情

```bash
# topic_id 从 URL 获取，如 https://www.v2ex.com/t/1234567
curl -s "https://www.v2ex.com/api/topics/show.json?id=TOPIC_ID" -H "User-Agent: agent-reach/1.0"
```

### 主题回复

```bash
curl -s "https://www.v2ex.com/api/replies/show.json?topic_id=TOPIC_ID&page=1" -H "User-Agent: agent-reach/1.0"
```

### 用户信息

```bash
curl -s "https://www.v2ex.com/api/members/show.json?username=USERNAME" -H "User-Agent: agent-reach/1.0"
```

### Python 调用示例

```python
from agent_reach.channels.v2ex import V2EXChannel

ch = V2EXChannel()

# 获取热门帖子
topics = ch.get_hot_topics(limit=10)
for t in topics:
    print(f"[{t['node_title']}] {t['title']} ({t['replies']} 回复)")

# 获取节点帖子
node_topics = ch.get_node_topics("python", limit=5)

# 获取帖子详情 + 回复
topic = ch.get_topic(1234567)
print(topic["title"], "—", topic["author"])

# 获取用户信息
user = ch.get_user("Livid")
```

> **节点列表**: https://www.v2ex.com/planes

## Reddit (rdt-cli)

```bash
# 搜索帖子
rdt search "query" --limit 10

# 读帖子全文 + 评论
rdt read POST_ID

# 浏览 subreddit
rdt sub python --limit 20

# 浏览热门
rdt popular --limit 10

# 浏览 /r/all
rdt all --limit 10
```

> **安装**: `pipx install rdt-cli`（确保 v0.4.2+）。无需登录即可搜索和阅读。
> 需要登录的功能：`rdt feed --subs-only`（订阅列表）、`rdt saved`（收藏）。
> 建议使用 `--yaml` 输出，对 AI agent 更友好。
