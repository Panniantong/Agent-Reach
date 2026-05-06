# -*- coding: utf-8 -*-
"""
HiveReach — installer, doctor, and configuration tool.

HiveReach helps AI agents install and configure upstream platform tools
(twitter-cli, yt-dlp, mcporter, gh CLI, etc.). After installation, agents
call the upstream tools directly — no wrapper layer needed.

Usage:
    from hivereach.doctor import check_all, format_report
    from hivereach.config import Config

    config = Config()
    results = check_all(config)
    print(format_report(results))
"""

from typing import Dict, Optional

from hivereach.config import Config


class HiveReach:
    """Give your AI Agent eyes to see the entire internet.

    This class provides health-check functionality.
    For reading/searching, use the upstream tools directly
    (see SKILL.md for commands).
    """

    def __init__(self, config: Optional[Config] = None):
        self.config = config or Config()

    def doctor(self) -> Dict[str, dict]:
        """Check all channel availability."""
        from hivereach.doctor import check_all
        return check_all(self.config)

    def doctor_report(self) -> str:
        """Get formatted health report."""
        from hivereach.doctor import check_all, format_report
        return format_report(check_all(self.config))
