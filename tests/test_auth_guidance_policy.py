"""Documentation must preserve the project's explicit auth boundaries."""

from __future__ import annotations

import re
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


def test_public_guidance_uses_official_opencli_extension_releases():
    """Never direct users to the outdated, unaffiliated Web Store build."""
    all_text = "\n".join(
        path.read_text(encoding="utf-8") for path in _policy_documents()
    )
    assert "chromewebstore.google.com/detail/opencli/" not in all_text

    install_guide = (ROOT / "docs" / "install.md").read_text(encoding="utf-8")
    assert "github.com/jackwener/opencli/releases" in install_guide
    assert "chrome://extensions" in install_guide
    assert "加载已解压的扩展程序" in install_guide


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


def test_localized_readmes_do_not_advertise_retired_channels():
    """Japanese and Korean docs must match the channels shipped by the CLI."""
    for path in (ROOT / "docs" / "README_ja.md", ROOT / "docs" / "README_ko.md"):
        text = path.read_text(encoding="utf-8").lower()
        assert "douyin" not in text, path.relative_to(ROOT)
        assert "weibo" not in text, path.relative_to(ROOT)


def test_public_guidance_never_installs_the_unrelated_pypi_package():
    """The PyPI name is owned by another project; GitHub URLs are required."""
    candidates = _policy_documents() + [
        ROOT / "agent_reach" / "integrations" / "mcp_server.py",
    ]
    bare_install = re.compile(
        r"\bpip\s+install(?:\s+--upgrade)?\s+['\"]?agent-reach(?:\[[^\]]+\])?\b",
        re.IGNORECASE,
    )
    violations = []
    for path in candidates:
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), 1
        ):
            if bare_install.search(line) and (
                "github.com/Panniantong/agent-reach" not in line
            ):
                violations.append(
                    f"{path.relative_to(ROOT)}:{line_number}: {line.strip()}"
                )

    assert not violations, "\n".join(violations)


def test_public_guidance_never_puts_secrets_in_process_arguments():
    """Operational docs should use hidden prompts or stdin for credentials."""
    forbidden = (
        'agent-reach configure twitter-cookies "',
        "agent-reach configure twitter-cookies '",
        'agent-reach configure xhs-cookies "',
        "agent-reach configure xhs-cookies '",
        "agent-reach configure groq-key gsk_",
        "agent-reach configure openai-key sk-",
        "agent-reach configure github-token gh",
        "agent-reach configure proxy http",
    )
    violations = []
    for path in _policy_documents():
        text = path.read_text(encoding="utf-8")
        for marker in forbidden:
            if marker in text:
                violations.append(f"{path.relative_to(ROOT)}: {marker}")

    assert not violations, "\n".join(violations)


def test_skill_explains_unverified_backend_state():
    """A null backend is an explicit safety state, not a routing instruction."""
    skills = (
        ROOT / "agent_reach" / "skill" / "SKILL.md",
        ROOT / "agent_reach" / "skill" / "SKILL_en.md",
    )
    for path in skills:
        text = path.read_text(encoding="utf-8")
        assert "active_backend: null" in text, path.relative_to(ROOT)
        assert "Doctor" in text, path.relative_to(ROOT)


def test_video_reference_has_content_level_youtube_fallbacks():
    """Version-only health must not be presented as proof subtitles work."""
    text = (
        ROOT / "agent_reach" / "skill" / "references" / "video.md"
    ).read_text(encoding="utf-8")
    assert "opencli youtube transcript" in text
    assert "最多重试 3 次" in text
    assert "agent-reach transcribe" in text


def test_skill_routes_finance_and_documents_opencli_discovery():
    skills = (
        ROOT / "agent_reach" / "skill" / "SKILL.md",
        ROOT / "agent_reach" / "skill" / "SKILL_en.md",
    )
    for path in skills:
        text = path.read_text(encoding="utf-8")
        assert "references/finance.md" in text, path.relative_to(ROOT)
        assert "opencli list" in text, path.relative_to(ROOT)
        assert "--help" in text, path.relative_to(ROOT)

    finance = ROOT / "agent_reach" / "skill" / "references" / "finance.md"
    text = finance.read_text(encoding="utf-8")
    assert "opencli xueqiu stock" in text
    assert "agent-reach configure --from-browser chrome --platform xueqiu" in text
