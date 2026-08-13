# -*- coding: utf-8 -*-
"""RSS — check if feedparser is available."""

from .base import Channel


class RSSChannel(Channel):
    name = "rss"
    description = "RSS/Atom 订阅源"
    backends = ["feedparser"]
    tier = 0
    reference = "web"
    url_commands = {
        "feedparser": (
            'python -c "import feedparser,sys;'
            '[print(e.title, e.link) for e in feedparser.parse(sys.argv[1]).entries[:10]]"'
            ' "{url}"'
        )
    }

    def can_handle(self, url: str) -> bool:
        return any(x in url.lower() for x in ["/feed", "/rss", ".xml", "atom"])

    def check(self, config=None):
        try:
            import feedparser  # noqa: F401
        except ImportError:
            self.active_backend = None
            return "off", "feedparser 未安装。安装：pip install feedparser"
        except Exception as e:
            # 已安装但导入期崩溃（半残安装/版本冲突）→ 重装处方
            self.active_backend = None
            return "error", f"feedparser 导入失败：{e}\n修复：pip install --force-reinstall feedparser"
        self.active_backend = self.backends[0]
        return "ok", "可读取 RSS/Atom 源"
