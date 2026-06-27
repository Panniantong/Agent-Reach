# -*- coding: utf-8 -*-
"""OKX — crypto news search and sentiment tracking via okx-trade-cli."""

import json
import shutil
import subprocess
from typing import Any
from urllib.parse import urlparse

from agent_reach.probe import probe_command
from agent_reach.utils.process import utf8_subprocess_env

from .base import Channel

_OKX_PACKAGE = "@okx_ai/okx-trade-cli"
_OKX_NPX_SPEC = f"{_OKX_PACKAGE}@latest"
_NPX_BACKEND = f"npx {_OKX_NPX_SPEC}"
_OKX_BROKEN_HINT = (
    "okx 命令存在但无法执行（node 环境损坏），重装：\n"
    f"  npm install -g {_OKX_PACKAGE}"
)


def _add_option(args: list[str], flag: str, value: Any) -> None:
    if value is None or value == "":
        return
    args.extend([flag, str(value)])


def _run_command(cmd: list[str], timeout: int = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        env=utf8_subprocess_env(),
    )


class OkxChannel(Channel):
    name = "okx"
    description = "OKX 加密新闻与情绪追踪"
    backends = ["okx CLI", _NPX_BACKEND]
    tier = 1

    def can_handle(self, url: str) -> bool:
        d = urlparse(url).netloc.lower()
        return "okx.com" in d

    def check(self, config=None):
        """Probe OKX CLI availability and lightweight credential state."""
        self.active_backend = None
        findings = []

        for backend in self.ordered_backends(config):
            if backend == "okx CLI":
                result = self._check_okx_cli()
            else:
                result = self._check_npx()
            if result is None:
                continue

            findings.append((backend, *result))

        broken_notes = [m for _, s, m in findings if s == "error"]

        for wanted in ("ok", "warn"):
            for backend, status, message in findings:
                if status != wanted:
                    continue
                self.active_backend = backend
                if broken_notes:
                    message += "\n[备选后端异常] " + "；".join(broken_notes)
                return status, message

        if findings:
            return "error", "\n".join(m for _, _, m in findings)

        return "off", (
            "OKX CLI 未安装。安装：\n"
            f"  npm install -g {_OKX_PACKAGE}\n"
            "或临时使用：\n"
            f"  npx {_OKX_NPX_SPEC} news search --keyword BTC --json"
        )

    def _check_okx_cli(self):
        probe = probe_command("okx", ["--version"], timeout=10, package=_OKX_PACKAGE)
        if probe.status == "missing":
            return None
        if probe.status == "broken":
            return "error", _OKX_BROKEN_HINT
        if probe.status == "timeout":
            return "warn", "okx CLI 状态检查超时，运行 `okx --version` 查看详情"
        if not probe.ok:
            return "error", f"okx CLI 执行异常：{probe.output or probe.status}"

        okx = shutil.which("okx") or "okx"
        return self._check_configured([okx])

    def _check_npx(self):
        probe = probe_command("npx", ["--version"], timeout=10, package="npm")
        if probe.status == "missing":
            return None
        if probe.status == "broken":
            return "error", "npx 命令存在但无法执行。请重装 Node.js/npm 后再试。"
        if not probe.ok:
            return "warn", f"npx 可用性未知（{probe.hint or probe.output or probe.status}）"
        return (
            "warn",
            "未检测到全局 okx CLI；可用 npx 临时执行 OKX 新闻/情绪命令。"
            f"首次使用前可运行 `npx {_OKX_NPX_SPEC} config init`，"
            "或全局安装后运行 `okx config init`。"
        )

    def _check_configured(self, prefix: list[str]):
        try:
            result = _run_command([*prefix, "config", "show", "--json"], timeout=10)
        except subprocess.TimeoutExpired:
            return "warn", "okx CLI 可用，但配置检查超时；运行 `okx config show` 查看详情"
        except OSError:
            return "error", _OKX_BROKEN_HINT

        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip().splitlines()
            tail = detail[-1] if detail else "无输出"
            return "warn", f"okx CLI 可用，但配置状态未知：{tail}"

        try:
            data = json.loads(result.stdout or "{}")
        except json.JSONDecodeError:
            return "warn", "okx CLI 可用，但配置输出无法解析；运行 `okx config show` 查看详情"

        profiles = data.get("profiles") if isinstance(data, dict) else None
        if isinstance(profiles, dict) and profiles:
            return "ok", "OKX CLI 可用（新闻搜索、币种情绪、情绪排行）"
        return (
            "warn",
            "OKX CLI 已安装但未配置凭据/登录。运行 `okx config init`，"
            f"或按需安装官方 skill：npx {_OKX_NPX_SPEC} skill add okx-sentiment-tracker"
        )

    def _command_prefix(self) -> list[str]:
        okx = shutil.which("okx")
        if okx:
            return [okx]
        npx = shutil.which("npx")
        if npx:
            return [npx, _OKX_NPX_SPEC]
        return []

    def _run_json(self, args: list[str], timeout: int = 30) -> Any:
        prefix = self._command_prefix()
        if not prefix:
            raise RuntimeError(
                f"OKX CLI 未安装。运行 `npm install -g {_OKX_PACKAGE}` "
                f"或使用 `npx {_OKX_NPX_SPEC}`。"
            )

        cmd = [*prefix, *args]
        if "--json" not in cmd:
            cmd.append("--json")
        try:
            result = _run_command(cmd, timeout=timeout)
        except subprocess.TimeoutExpired as e:
            raise RuntimeError(f"okx CLI 响应超时（>{timeout}s）") from e
        except OSError as e:
            raise RuntimeError(_OKX_BROKEN_HINT) from e

        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip().splitlines()
            tail = detail[-1] if detail else f"exit {result.returncode}"
            raise RuntimeError(f"okx CLI 执行失败：{tail}")
        try:
            return json.loads(result.stdout or "null")
        except json.JSONDecodeError as e:
            raise RuntimeError("okx CLI 未返回有效 JSON") from e

    def get_latest_news(
        self,
        coins: str | None = None,
        platform: str | None = None,
        language: str = "en-US",
        limit: int = 20,
    ) -> Any:
        """Get latest crypto news."""
        args = ["news", "latest"]
        _add_option(args, "--coins", coins)
        _add_option(args, "--platform", platform)
        _add_option(args, "--lang", language)
        _add_option(args, "--limit", limit)
        return self._run_json(args)

    def search_news(
        self,
        keyword: str,
        coins: str | None = None,
        sentiment: str | None = None,
        platform: str | None = None,
        language: str = "en-US",
        limit: int = 20,
    ) -> Any:
        """Search crypto news with optional coin and sentiment filters."""
        args = ["news", "search"]
        _add_option(args, "--keyword", keyword)
        _add_option(args, "--coins", coins)
        _add_option(args, "--sentiment", sentiment)
        _add_option(args, "--platform", platform)
        _add_option(args, "--lang", language)
        _add_option(args, "--limit", limit)
        return self._run_json(args)

    def get_coin_sentiment(self, coins: str, period: str = "24h") -> Any:
        """Get current sentiment snapshot for one or more coins."""
        args = ["news", "coin-sentiment"]
        _add_option(args, "--coins", coins)
        _add_option(args, "--period", period)
        return self._run_json(args)

    def get_coin_trend(self, coin: str, period: str = "24h", points: int = 24) -> Any:
        """Get sentiment trend over time for one coin."""
        args = ["news", "coin-trend", coin]
        _add_option(args, "--period", period)
        _add_option(args, "--points", points)
        return self._run_json(args)

    def get_sentiment_rank(
        self,
        period: str = "24h",
        sort_by: str | None = None,
        limit: int = 20,
    ) -> Any:
        """Get coin ranking by social hotness or sentiment direction."""
        args = ["news", "sentiment-rank"]
        _add_option(args, "--period", period)
        _add_option(args, "--sort-by", sort_by)
        _add_option(args, "--limit", limit)
        return self._run_json(args)
