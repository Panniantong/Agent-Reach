# 能力边界 / Capability scope

用户问"能查什么、查得全吗"，或要判断结果完整度时读这份。下表是声明能力，不代表所有网络、账号和内容都已实测。
Read when the user asks what can be fetched or how complete a result is. Declared capabilities, not guaranteed results.

## 三层说明

- **公开可尝试**：Agent 已有网页工具、原生工具或公开接口可能已满足任务；不要求安装浏览器、登录。按实际取得的证据回答。
- **Reach 补充**：当前发布版声明的动作，见 `agent-reach channels`。需要配置时先复用专用浏览器已保存的会话，所选路径实际要求登录时才本人登录。
- **本机已验证**：只列本机最近成功验收的具体动作；安装、保存会话和网络可达均不等于业务验收。

## 本版渠道

| 渠道 | 公开路径可尝试 | Reach 补充与边界 |
|---|---|---|
| GitHub | 公开仓库、README、Issue/PR | 仓库搜索、仓库/Issue/PR 读取和返回的评论；私有权限另行判断 |
| YouTube | 搜索、标题、简介；原生工具可能取得部分评论及字幕正文 | search/read/subtitle/transcribe；当前没有统一 comments 动作；轨道列表不等于字幕正文，无字幕时转录依赖相应工具 |
| B 站 | 搜索、简介；部分公开接口可返回评论及父子 ID | search/read/hot/subtitle；当前没有统一 comments 动作；字幕随视频和访问路径而异 |
| Reddit | 搜索、正文、部分评论；某些公开 JSON 可含父子 ID | 浏览器 search/read/subreddit；登录依所选路径决定，不保证完整评论树、全部回复；不提供发评论 |
| X/Twitter | 搜索命中的公开单帖；部分官方公开嵌入可返回全文 | search/profile/tweets/thread；单帖可读不代表回复流可读，不保证完整评论树 |
| 小红书 | 公开列表或索引可能有笔记 ID、作者、标题，空字段不能补猜 | search/read/comments；文字描述、顶级评论及已加载回复；不保证全部评论，不声称理解图片/视频 |
| Instagram | 部分索引和主页浅层信息；HTML 应用壳不算帖文 | search 搜用户、profile 主页、posts 指定用户帖子描述；无统一评论动作，不声称理解图片/视频 |
| Facebook | 部分索引或 HTML 摘要；摘要可能被截断 | search/profile；无统一详情或评论动作，不把搜索摘要当全文 |
| LinkedIn | 搜公开职位、读公开 JD | jobs/read 先尝试公开网页；指定 opencli 才直接走站内；不保证所有职位可读 |
| BOSS | 搜索索引中可能有职位摘要 | search/read 职位列表与 JD；不能根据编码薪资猜数字；详情后备能力依渠道声明 |
| V2EX | 主题、正文及公开回复 | hot/node/read/user；返回范围以本次响应为准，不保证隐藏或缺失回复 |
| 雪球 | 部分公开行情和索引信息 | quote/search/hot_posts/hot_stocks；行情与社区路径分别验收 |
| Web | Agent 自带搜索/读取 | Reach web search/read 为匿名保底；摘要、页面壳和验证页不能当完整正文 |
| 小宇宙 | 节目页标题、简介 | transcribe 整集转文字；需要用户提供 Groq Key（`agent-reach configure groq-key`） |

登录后的能力表述使用“可启用/尝试上述浏览器动作”，不使用“登录后支持全部评论”。用户跳过登录时交付已有公开证据。
