# 金融行情

雪球股票行情、搜索与热门内容。行情可能延迟，不构成投资建议。

## 先检查状态

```bash
agent-reach doctor --json
```

`xueqiu.active_backend` 有值时按该后端使用；值为 `null` 只表示 Doctor 没有完成
实时内容验证。登录身份与匿名会话是否可用需要分别验证，不能把 HTTP 400
当成股票不存在，也不能仅据此判断 Cookie 过期。

## OpenCLI（桌面已有 Chrome 登录态时优先）

```bash
# 验证当前登录态
opencli xueqiu whoami -f yaml

# 股票搜索与实时行情
opencli xueqiu search "英伟达" -f yaml
opencli xueqiu stock NVDA -f yaml

# 热门内容与热门股票
opencli xueqiu hot -f yaml
opencli xueqiu hot-stock -f yaml

# 查看全部只读命令
opencli xueqiu --help
```

OpenCLI 只复用用户已经存在且明确控制的浏览器会话。不要自动执行
`opencli xueqiu login`；没有现成登录态时，让用户先在 Chrome 登录，或显式导入
雪球所需的最小 Cookie：

```bash
agent-reach configure --from-browser chrome --platform xueqiu
```

该配置只读取并保存 `xq_a_token`，不会顺带采集其他平台 Cookie。

## 验收与失败处理

- 以返回股票名称、代码、价格或非空内容列表为成功；退出码 0 但字段为空不算成功。
- `error_code=400016` 表示当前会话被拒绝，不足以单独证明 Cookie 过期；
  网络错误和其他 HTTP 400 需要分别排查。
- `whoami` 成功而 `stock`/`hot` 失败时，按适配器解析或平台接口问题报告，不要误诊成未登录。

### 停止使用已保存的 API Cookie

此处只适用于 Agent Reach 的雪球 API 路径，不会修复 OpenCLI 浏览器登录态。
当 doctor 提示正在使用 `config.yaml` 中保存的 Cookie，且用户明确决定停止
使用它时，运行：

```bash
agent-reach configure --unset xueqiu-cookie
```

只移除 `xueqiu_cookie`，保留其他配置；不清除浏览器 Cookie，不修改环境变量。
`XUEQIU_COOKIE` 仍设置时可能继续提供凭据，用户应在自己控制的运行环境中
移除或更新它，不要输出凭据值。已有进程可能缓存旧会话，请在新进程中重试。

清除后会尝试匿名会话，但不保证访问恢复；匿名入口问题与 Cookie 清除是
两件事，入口修复见 [PR #667](https://github.com/Panniantong/Agent-Reach/pull/667)。
以实际非空内容验收。不要自动清除凭据、导入浏览器 Cookie或在失败时切换身份。
