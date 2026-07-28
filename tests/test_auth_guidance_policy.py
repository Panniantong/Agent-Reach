"""Documentation must preserve the project's explicit auth boundaries."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _policy_documents() -> list[Path]:
    documents = list(ROOT.glob("README*.md"))
    for directory in (
        ROOT / "docs",
        ROOT / "agent_reach" / "guides",
        ROOT / "agent_reach" / "skill",
    ):
        documents.extend(directory.rglob("*.md"))
    return sorted(set(documents))


def test_xiaohongshu_guidance_never_starts_implicit_login():
    """Do not reintroduce QR or automatic browser-cookie login guidance."""
    xhs_markers = ("xiaohongshu", "小红书", "小紅書", "xhs")
    legacy_auth_markers = (
        "扫码",
        "二维码",
        "qr login",
        "qr scan",
        "qrcode",
        "ブラウザからcookieを自動抽出",
        "브라우저에서 cookie 자동 추출",
    )
    forbidden_commands = (
        "xhs " + "login",
        "get_login_" + "qrcode",
    )

    violations = []
    for path in _policy_documents():
        text = path.read_text(encoding="utf-8")
        lowered = text.lower()
        for command in forbidden_commands:
            if command in lowered:
                violations.append(f"{path.relative_to(ROOT)}: {command}")
        for line_number, line in enumerate(lowered.splitlines(), 1):
            if not any(marker in line for marker in xhs_markers):
                continue
            if any(marker in line for marker in legacy_auth_markers):
                violations.append(
                    f"{path.relative_to(ROOT)}:{line_number}: {line.strip()}"
                )

    assert not violations, "\n".join(violations)


def test_xiaohongshu_opencli_and_export_boundaries_are_truthful():
    """Cookie import is for MCP/legacy tools, never OpenCLI or Chrome."""
    boundary_docs = (
        ROOT / "docs" / "install.md",
        ROOT / "agent_reach" / "guides" / "setup-xiaohongshu.md",
        ROOT / "agent_reach" / "skill" / "references" / "social.md",
    )
    for path in boundary_docs:
        text = path.read_text(encoding="utf-8")
        assert "已经存在且明确控制" in text, path.relative_to(ROOT)
        assert "不会把 Cookie 注入 OpenCLI" in text, path.relative_to(ROOT)

    xhs_guide = boundary_docs[1].read_text(encoding="utf-8")
    assert "xiaohongshu.com 同域 Cookie 集" in xhs_guide
    assert "非 xiaohongshu.com 域 Cookie" in xhs_guide


def test_twitter_operational_docs_explain_the_environment_boundary():
    """Saved cookies help doctor only; direct twitter commands need env vars."""
    operational_docs = (
        ROOT / "README.md",
        ROOT / "docs" / "README_en.md",
        ROOT / "docs" / "README_ja.md",
        ROOT / "docs" / "README_ko.md",
        ROOT / "docs" / "cookie-export.md",
        ROOT / "docs" / "install.md",
        ROOT / "docs" / "troubleshooting.md",
        ROOT / "agent_reach" / "guides" / "setup-twitter.md",
        ROOT / "agent_reach" / "skill" / "SKILL.md",
        ROOT / "agent_reach" / "skill" / "SKILL_en.md",
        ROOT / "agent_reach" / "skill" / "references" / "social.md",
    )

    for path in operational_docs:
        text = path.read_text(encoding="utf-8")
        assert "TWITTER_AUTH_TOKEN" in text, path.relative_to(ROOT)
        assert "TWITTER_CT0" in text, path.relative_to(ROOT)

    twitter_guide = (
        ROOT / "agent_reach" / "guides" / "setup-twitter.md"
    ).read_text(encoding="utf-8")
    assert "不会执行 `twitter status`" in twitter_guide
    assert "不会修改当前 Shell" in twitter_guide
    assert "Export → Header String" in twitter_guide
    assert "cookie JSON" not in twitter_guide
    assert "复制全部" not in twitter_guide

    for expected in (
        "--sync-legacy-twitter",
        "~/.agent-reach/config.yaml",
        "~/.config/xfetch/session.json",
        "~/.config/bird/credentials.env",
    ):
        assert expected in twitter_guide
    assert "默认只写" in twitter_guide
    assert "不会自动删除" in twitter_guide

    rendered_as_verified = (
        "✅ Twitter/X tweets",
        "✅ Twitter/Xツイート",
        "✅ Twitter/X 트윗",
    )
    all_text = "\n".join(
        path.read_text(encoding="utf-8") for path in _policy_documents()
    )
    assert not any(claim in all_text for claim in rendered_as_verified)


def test_localized_readmes_keep_current_bilibili_and_xhs_routes():
    """Translations must not revive retired yt-dlp/Bilibili or XHS defaults."""
    readmes = (
        ROOT / "README.md",
        ROOT / "docs" / "README_en.md",
        ROOT / "docs" / "README_ja.md",
        ROOT / "docs" / "README_ko.md",
    )

    for path in readmes:
        text = path.read_text(encoding="utf-8")
        assert "bilibili.py     → yt-dlp" not in text, path.relative_to(ROOT)
        assert "YouTube + Bilibili" not in text, path.relative_to(ROOT)
        assert "bili-cli" in text, path.relative_to(ROOT)
        assert (
            "xiaohongshu.py  → OpenCLI ▸ xiaohongshu-mcp ▸ xhs-cli"
            in text
        ), path.relative_to(ROOT)
