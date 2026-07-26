# -*- coding: utf-8
"""Simple web dashboard for local 60s API (readable HTML, not raw JSON)."""

from __future__ import annotations

import json
import os
import signal
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse
from urllib.request import Request, urlopen

PORTAL_PORT = 8786
PORTAL_HOST = os.environ.get("AGENT_REACH_PORTAL_HOST", "0.0.0.0")
API_BASE_DEFAULT = "http://127.0.0.1:8787"


def portal_pid_file() -> Path:
    return Path.home() / ".agent-reach" / "daily_run" / "60s_portal.pid"


def _portal_html(api_base: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>60s 热点新闻面板</title>
  <style>
    :root {{
      color-scheme: light dark;
      --bg: #0f172a;
      --card: #111827;
      --text: #e5e7eb;
      --muted: #94a3b8;
      --accent: #38bdf8;
      --border: #1f2937;
    }}
    @media (prefers-color-scheme: light) {{
      :root {{
        --bg: #f8fafc;
        --card: #ffffff;
        --text: #0f172a;
        --muted: #64748b;
        --accent: #0284c7;
        --border: #e2e8f0;
      }}
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.6;
    }}
    .wrap {{ max-width: 960px; margin: 0 auto; padding: 24px 16px 48px; }}
    h1 {{ margin: 0 0 8px; font-size: 1.6rem; }}
    .sub {{ color: var(--muted); margin-bottom: 24px; }}
    .card {{
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 16px 18px;
      margin-bottom: 16px;
    }}
    .card h2 {{ margin: 0 0 12px; font-size: 1.1rem; }}
    ol {{ margin: 0; padding-left: 1.2rem; }}
    li {{ margin: 8px 0; }}
    .tip {{ margin-top: 12px; color: var(--muted); font-style: italic; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ text-align: left; padding: 8px 6px; border-bottom: 1px solid var(--border); }}
    th {{ color: var(--muted); font-weight: 600; }}
    a {{ color: var(--accent); text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    .err {{ color: #f87171; }}
    .links a {{ margin-right: 12px; }}
  </style>
</head>
<body>
  <div class="wrap">
    <h1>60s 热点新闻面板</h1>
    <p class="sub">Web 面板：<code>{PORTAL_PORT}</code> · API 后端：<code>{urlparse(api_base).netloc}</code></p>

    <div class="card">
      <h2>📰 每天 60 秒读懂世界</h2>
      <div id="daily">加载中…</div>
    </div>

    <div class="card">
      <h2>🔥 跨平台热搜</h2>
      <div id="hot">加载中…</div>
    </div>

    <div class="card links">
      <h2>API 快捷入口</h2>
      <a href="/v2/60s?encoding=text" target="_blank">今日要闻（纯文本）</a>
      <a href="/v2/60s?encoding=markdown" target="_blank">今日要闻（Markdown）</a>
      <a href="/v2/weibo?encoding=json" target="_blank">微博 JSON</a>
      <a href="{api_base}/" target="_blank">API 元数据（JSON）</a>
      <a href="https://docs.60s-api.viki.moe" target="_blank">官方文档</a>
    </div>
  </div>
  <script>
    const API = "";

    async function fetchJson(path) {{
      const res = await fetch(`${{API}}${{path}}`);
      if (!res.ok) throw new Error(`${{path}} HTTP ${{res.status}}`);
      return res.json();
    }}

    function renderDaily(payload) {{
      const data = payload.data || {{}};
      const news = data.news || [];
      const date = data.date || "今日";
      const tip = data.tip || "";
      const items = news.slice(0, 15).map((item, idx) => {{
        if (typeof item === "string") return `<li>${{item}}</li>`;
        const title = item.title || "";
        const link = item.link || "";
        return link
          ? `<li><a href="${{link}}" target="_blank" rel="noopener">${{title}}</a></li>`
          : `<li>${{title}}</li>`;
      }}).join("");
      document.getElementById("daily").innerHTML =
        `<ol>${{items}}</ol>` + (tip ? `<div class="tip">微语：${{tip}}</div>` : "");
    }}

    function renderHot(platform, rows) {{
      const body = rows.slice(0, 10).map(row => {{
        const title = row.title || row.word || "";
        const hot = row.hot_value ?? row.score ?? "";
        const link = row.link || row.url || "";
        const titleCell = link
          ? `<a href="${{link}}" target="_blank" rel="noopener">${{title}}</a>`
          : title;
        return `<tr><td>${{platform}}</td><td>${{titleCell}}</td><td>${{hot}}</td></tr>`;
      }}).join("");
      return body;
    }}

    async function loadHot() {{
      const platforms = [
        ["weibo", "/v2/weibo?encoding=json"],
        ["zhihu", "/v2/zhihu?encoding=json"],
        ["it-news", "/v2/it-news?encoding=json&limit=10"],
      ];
      let html = "<table><thead><tr><th>平台</th><th>标题</th><th>热度</th></tr></thead><tbody>";
      for (const [name, path] of platforms) {{
        try {{
          const payload = await fetchJson(path);
          html += renderHot(name, payload.data || []);
        }} catch (err) {{
          html += `<tr><td>${{name}}</td><td colspan="2" class="err">${{err.message}}</td></tr>`;
        }}
      }}
      html += "</tbody></table>";
      document.getElementById("hot").innerHTML = html;
    }}

    async function boot() {{
      try {{
        const payload = await fetchJson("/v2/60s?encoding=json");
        renderDaily(payload);
      }} catch (err) {{
        document.getElementById("daily").innerHTML = `<p class="err">加载失败：${{err.message}}</p>`;
      }}
      await loadHot();
    }}
    boot();
  </script>
</body>
</html>"""


class _PortalHandler(BaseHTTPRequestHandler):
    api_base: str = API_BASE_DEFAULT

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        return

    def _proxy_api(self) -> None:
        target = self.api_base.rstrip("/") + self.path
        try:
            req = Request(target, headers={"User-Agent": "agent-reach-portal/1.0"})
            with urlopen(req, timeout=30) as resp:
                body = resp.read()
                self.send_response(resp.status)
                content_type = resp.headers.get("Content-Type")
                if content_type:
                    self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
        except Exception as exc:
            message = str(exc).encode("utf-8", errors="replace")
            self.send_response(502)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(message)))
            self.end_headers()
            self.wfile.write(message)

    def do_GET(self) -> None:  # noqa: N802
        if self.path in ("/", "/index.html"):
            body = _portal_html(self.api_base).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == "/health":
            body = b"ok"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path.startswith("/v2/"):
            self._proxy_api()
            return
        self.send_error(404)


def portal_running() -> bool:
    pid = read_portal_pid()
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        portal_pid_file().unlink(missing_ok=True)
        return False


def read_portal_pid() -> Optional[int]:
    path = portal_pid_file()
    if not path.exists():
        return None
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def _portal_url(port: int = PORTAL_PORT) -> str:
    if PORTAL_HOST in ("0.0.0.0", "::"):
        return f"http://127.0.0.1:{port} (LAN: http://<本机IP>:{port})"
    return f"http://{PORTAL_HOST}:{port}"


def start_portal(*, api_base: str = API_BASE_DEFAULT, force: bool = False) -> tuple[bool, str]:
    import subprocess
    import sys

    if portal_running() and not force:
        return True, f"portal already running (pid {read_portal_pid()}) on {_portal_url()}"

    if force:
        stop_portal()

    portal_pid_file().parent.mkdir(parents=True, exist_ok=True)
    log_path = Path.home() / ".agent-reach" / "daily_run" / "logs" / "60s_portal.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable,
        "-m",
        "agent_reach.daily_run.hot_news_portal",
        "serve",
        "--api-base",
        api_base.rstrip("/"),
        "--host",
        PORTAL_HOST,
        "--port",
        str(PORTAL_PORT),
    ]
    try:
        with open(log_path, "ab") as logfh:
            proc = subprocess.Popen(
                cmd,
                stdout=logfh,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        portal_pid_file().write_text(str(proc.pid) + "\n", encoding="utf-8")
        return True, f"portal running at {_portal_url()}"
    except (OSError, subprocess.SubprocessError) as exc:
        return False, str(exc)


def run_portal_server(*, api_base: str, host: str = PORTAL_HOST, port: int = PORTAL_PORT) -> None:
    handler = type("Handler", (_PortalHandler,), {"api_base": api_base.rstrip("/")})
    server = ThreadingHTTPServer((host, port), handler)
    server.serve_forever(poll_interval=0.5)


def stop_portal() -> tuple[bool, str]:
    pid = read_portal_pid()
    if not pid:
        return True, "portal not running"
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        pass
    portal_pid_file().unlink(missing_ok=True)
    return True, "stopped portal"


def _cli() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="60s web portal")
    parser.add_argument("action", choices=["serve"])
    parser.add_argument("--api-base", default=API_BASE_DEFAULT)
    parser.add_argument("--host", default=PORTAL_HOST)
    parser.add_argument("--port", type=int, default=PORTAL_PORT)
    args = parser.parse_args()
    if args.action == "serve":
        run_portal_server(api_base=args.api_base, host=args.host, port=args.port)


if __name__ == "__main__":
    _cli()
