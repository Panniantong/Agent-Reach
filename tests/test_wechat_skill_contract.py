"""Regression checks for discovery, routing and WeChat command examples."""

import re
import shlex
from pathlib import Path

import pytest
import yaml

SKILL = Path(__file__).resolve().parents[1] / "agent_reach/skill"


@pytest.mark.parametrize("locale", ["SKILL.md", "SKILL_en.md"])
def test_wechat_is_discoverable_and_routes_to_existing_references(locale):
    content = (SKILL / locale).read_text(encoding="utf-8")
    frontmatter = yaml.safe_load(content.split("---", 2)[1])
    description = frontmatter["description"]
    assert "微信公众号" in description and "WeChat" in description
    assert len(description) <= 1024
    links = re.findall(r"\]\((references/(?:search|web)\.md)#([^)]*公众号[^)]*)\)", content)
    assert len(links) == 2
    for relative, heading in links:
        assert f"## {heading}" in (SKILL / relative).read_text(encoding="utf-8")


def test_wechat_search_examples_keep_domain_and_objective_in_single_arguments():
    search = (SKILL / "references/search.md").read_text(encoding="utf-8")
    section = search.split("## 微信公众号文章搜索", 1)[1].split("\n## ", 1)[0]
    commands = [
        shlex.split(line) for line in section.splitlines() if line.startswith("mcporter call ")
    ]
    assert len(commands) >= 2
    for args in commands:
        query = next(arg.split("=", 1)[1] for arg in args if arg.startswith("query="))
        objective = next(arg.split("=", 1)[1] for arg in args if arg.startswith("objective="))
        assert "site:mp.weixin.qq.com" in query
        assert "mp.weixin.qq.com" in objective or "原文链接" in objective
        assert args[args.index("--timeout") + 1] == "30000"
    assert "本次实际搜索结果" in section
    assert "Highlights" in section


def test_wechat_reading_is_schema_gated_and_has_bounded_fallback():
    web = (SKILL / "references/web.md").read_text(encoding="utf-8")
    section = web.split("## 微信公众号正文读取", 1)[1].split("\n## ", 1)[0]
    fetch = next(
        shlex.split(line) for line in section.splitlines() if line.startswith("mcporter call ")
    )
    assert fetch[:3] == ["mcporter", "call", "exa.web_fetch_exa"]
    assert "urls=ARTICLE_URL" in fetch
    assert "maxCharacters=8000" in fetch
    assert "mcporter list exa --schema" in section
    curl = next(shlex.split(line) for line in section.splitlines() if line.startswith("curl "))
    assert curl[curl.index("--max-time") + 1] == "30"
    assert "部分正文" in section and "只有检索摘录" in section
    assert "不要自动登录" in section
