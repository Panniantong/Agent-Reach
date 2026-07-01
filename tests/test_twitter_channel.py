# -*- coding: utf-8 -*-

from unittest.mock import Mock, patch

from agent_reach.channels.twitter import TwitterChannel


def _cp(stdout="", stderr="", returncode=0):
    m = Mock()
    m.stdout = stdout
    m.stderr = stderr
    m.returncode = returncode
    return m


# --- twitter-cli tests ---

def test_check_twitter_cli_found_and_auth_ok():
    """twitter-cli found + twitter status ok → ok."""
    channel = TwitterChannel()
    with patch("shutil.which", side_effect=lambda name: "/usr/local/bin/twitter" if name == "twitter" else None), patch(
        "subprocess.run",
        return_value=_cp(stdout="ok: true\nusername: testuser\n", returncode=0),
    ):
        status, message = channel.check()
    assert status == "ok"
    assert "twitter-cli" in message
    assert "完整可用" in message
    assert channel.active_backend == "twitter-cli"


def test_check_twitter_cli_found_auth_missing():
    """twitter-cli found + not_authenticated → warn about auth."""
    channel = TwitterChannel()
    with patch("shutil.which", side_effect=lambda name: "/usr/local/bin/twitter" if name == "twitter" else None), patch(
        "subprocess.run",
        return_value=_cp(
            stderr="ok: false\nerror:\n  code: not_authenticated\n",
            returncode=1,
        ),
    ):
        status, message = channel.check()
    assert status == "warn"
    assert "未认证" in message
    # 未认证是业务态：工具进程活着，后端仍可用
    assert channel.active_backend == "twitter-cli"


# --- bird CLI fallback tests ---

def test_check_bird_fallback_auth_ok():
    """No twitter-cli, but bird found + bird check ok → ok."""
    channel = TwitterChannel()
    def which_side_effect(name):
        if name == "bird":
            return "/usr/local/bin/bird"
        return None
    with patch("shutil.which", side_effect=which_side_effect), patch(
        "subprocess.run",
        return_value=_cp(stdout="Authenticated as @user\n", returncode=0),
    ):
        status, message = channel.check()
    assert status == "ok"
    assert "bird" in message
    assert channel.active_backend == "bird CLI (legacy)"


def test_check_bird_fallback_auth_missing():
    """No twitter-cli, bird found but Missing credentials → warn."""
    channel = TwitterChannel()
    def which_side_effect(name):
        if name == "bird":
            return "/usr/local/bin/bird"
        return None
    with patch("shutil.which", side_effect=which_side_effect), patch(
        "subprocess.run",
        return_value=_cp(stderr="Missing credentials\n", returncode=1),
    ):
        status, message = channel.check()
    assert status == "warn"
    assert "未配置认证" in message


# --- neither installed ---

def test_check_nothing_installed():
    """Neither twitter-cli nor bird → warn with install hint."""
    channel = TwitterChannel()
    with patch("shutil.which", return_value=None):
        status, message = channel.check()
    assert status == "warn"
    assert "twitter-cli" in message
    assert channel.active_backend is None


# --- twitter-cli preferred over bird ---

def test_twitter_cli_preferred_over_bird():
    """When both are installed, twitter-cli is used."""
    channel = TwitterChannel()
    def which_side_effect(name):
        if name == "twitter":
            return "/usr/local/bin/twitter"
        if name == "bird":
            return "/usr/local/bin/bird"
        return None
    with patch("shutil.which", side_effect=which_side_effect), patch(
        "subprocess.run",
        return_value=_cp(stdout="ok: true\n", returncode=0),
    ):
        status, message = channel.check()
    assert status == "ok"
    assert "twitter-cli" in message
    assert channel.active_backend == "twitter-cli"


# --- broken install (stale venv shim) ---

def test_check_twitter_cli_broken_reports_error_with_reinstall_hint():
    """which 命中但 exec 抛 FileNotFoundError（venv 断链）→ error + 重装处方。"""
    channel = TwitterChannel()
    with patch(
        "shutil.which",
        side_effect=lambda name: "/usr/local/bin/twitter" if name == "twitter" else None,
    ), patch("subprocess.run", side_effect=FileNotFoundError("/usr/local/bin/twitter")):
        status, message = channel.check()
    assert status == "error"
    assert "无法执行" in message
    assert "uv tool install --force twitter-cli" in message
    assert "pipx reinstall twitter-cli" in message
    assert channel.active_backend is None


def test_check_twitter_cli_broken_falls_back_to_bird():
    """twitter-cli 断链但 bird 健康 → 回退到 bird，后端正确归属。"""
    channel = TwitterChannel()

    def which_side_effect(name):
        if name in ("twitter", "bird"):
            return f"/usr/local/bin/{name}"
        return None

    def run_side_effect(cmd, **kwargs):
        if "twitter" in cmd[0]:
            raise FileNotFoundError(cmd[0])
        return _cp(stdout="Authenticated as @user\n", returncode=0)

    with patch("shutil.which", side_effect=which_side_effect), patch(
        "subprocess.run", side_effect=run_side_effect
    ):
        status, message = channel.check()
    assert status == "ok"
    assert "bird" in message
    assert channel.active_backend == "bird CLI (legacy)"


def test_unauthenticated_twitter_cli_does_not_block_working_opencli():
    """warn 候选不得屏蔽排在后面的 ok 候选(Codex review 发现)。"""
    channel = TwitterChannel()
    with patch.object(
        TwitterChannel, "_check_twitter_cli",
        return_value=("warn", "twitter-cli 已安装但未认证"),
    ), patch.object(
        TwitterChannel, "_check_opencli",
        return_value=("ok", "OpenCLI 可用（复用浏览器登录态）"),
    ), patch.object(TwitterChannel, "_check_bird", return_value=None):
        status, msg = channel.check()
    assert status == "ok"
    assert channel.active_backend == "OpenCLI"


def test_all_warn_falls_back_to_first_warn():
    channel = TwitterChannel()
    with patch.object(
        TwitterChannel, "_check_twitter_cli",
        return_value=("warn", "twitter-cli 未认证"),
    ), patch.object(
        TwitterChannel, "_check_opencli",
        return_value=("warn", "扩展未连接"),
    ), patch.object(TwitterChannel, "_check_bird", return_value=None):
        status, msg = channel.check()
    assert status == "warn"
    assert channel.active_backend == "twitter-cli"
    assert "未认证" in msg
