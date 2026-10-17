# 维护 / Maintenance

仅在故障、依赖修复、升级或卸载时加载。Load only for diagnosis, repair, updates or uninstall.

## 有界诊断 / Bounded diagnosis

`agent-reach doctor --text` reads local status. For a live query test, use `agent-reach check CHANNEL --search --text`; do not test every backend merely to answer one search request.

- NEED_SETUP: follow the returned setup hint. Installation is not login verification.
- NEED_LOGIN: stop this request and read [Sessions](sessions.md). The user performs any required login.
- PLATFORM_BLOCKED / RATE_LIMITED / BUSY: stop; do not switch accounts or backends to keep requesting.
- UPSTREAM_BROKEN / TIMEOUT: report the recorded attempts and failure. Do not retry in a loop.
- BAD_INPUT / NOT_FOUND: check the requested action and URL before another request.

Reach may try a configured fallback for non-final errors within its total deadline. This does not authorize the Agent to repeat a failed command or bypass a final error.

`agent-reach browser repair-opencli` is an explicit repair for the version/hash-checked XHS wait-time patch. Never patch dependencies during an ordinary query.

## 更新与发布 / Updates and distribution

更新前确认安装来源。源码或 wheel 安装的构建应从对应来源更新；仅复制 Skill 不会更新运行时。发布包必须携带 `skill/references/*.md`。

An update notice is not authorization to upgrade. After the user agrees, identify the build source and update from the same source. If the matching artifact is unavailable, report that gap instead of replacing the build.

首次 `setup` 尚未默认安装所有可选渠道，也不会自动导入登录态。不要把计划中的初始化向导当作现有功能。

## 删除 / Removal

Logout semantics differ by backend; read [Sessions](sessions.md) first. `remove CHANNEL` removes the channel and its owned resources, not the user's original browser profile.

Before uninstalling, show `agent-reach uninstall --dry-run`. Execute uninstall only within the user's authorized scope. Preserve unrelated files and original browser state.
