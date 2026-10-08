"""Credential recovery is explicit, local-only, bounded and secret-free."""

import io
import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError

import pytest
import yaml

from agent_reach import cli
from agent_reach.channels import xueqiu as xq
from agent_reach.config import Config


@pytest.fixture(autouse=True)
def no_host_credentials(monkeypatch):
    monkeypatch.delenv("XUEQIU_COOKIE", raising=False)
    monkeypatch.setattr(xq, "_cookie_source", None, raising=False)


def run_cli(monkeypatch, *args):
    monkeypatch.setattr(sys, "argv", ["agent-reach", "configure", *args])
    monkeypatch.setattr(cli, "_configure_logging", lambda *_args: None)
    cli.main()


def test_unset_removes_only_saved_cookie(monkeypatch, capsys):
    cfg = Config()
    cfg.set("xueqiu_cookie", "xq_a_token=SECRET-cookie")
    cfg.set("unrelated", {"list": [1, "保留"], "enabled": True})
    cfg.set("github_token", "SECRET-other")
    monkeypatch.setattr(xq._opener, "open", lambda *_a, **_k: pytest.fail("network"))
    monkeypatch.setattr(cli, "_read_configure_value", lambda *_a: pytest.fail("input"))
    run_cli(monkeypatch, "--unset", "xueqiu-cookie")
    assert Config().data == {
        "unrelated": {"list": [1, "保留"], "enabled": True},
        "github_token": "SECRET-other",
    }
    output = capsys.readouterr()
    assert "Removed" in output.out
    assert "SECRET" not in output.out + output.err
    before = cfg.config_path.read_bytes()
    run_cli(monkeypatch, "--unset", "xueqiu-cookie")
    assert cfg.config_path.read_bytes() == before


def test_unset_missing_config_creates_nothing(monkeypatch, capsys):
    run_cli(monkeypatch, "--unset", "xueqiu-cookie")
    assert not Config.CONFIG_DIR.exists()
    assert "No saved" in capsys.readouterr().out


def test_unset_reports_environment_without_mutating_it(monkeypatch, capsys):
    cfg = Config()
    cfg.set("xueqiu_cookie", "xq_a_token=FILE-secret")
    monkeypatch.setenv("XUEQIU_COOKIE", "xq_a_token=ENV-secret")
    run_cli(monkeypatch, "--unset", "xueqiu-cookie")
    output = capsys.readouterr().out
    assert "XUEQIU_COOKIE" in output and "still" in output
    assert "secret" not in output
    assert Config().get("xueqiu_cookie") == "xq_a_token=ENV-secret"
    assert os.environ["XUEQIU_COOKIE"] == "xq_a_token=ENV-secret"


def test_env_only_clear_warns_without_creating_config(monkeypatch, capsys):
    monkeypatch.setenv("XUEQIU_COOKIE", "xq_a_token=ENV-secret")
    run_cli(monkeypatch, "--unset", "xueqiu-cookie")
    assert not Config.CONFIG_DIR.exists()
    assert "XUEQIU_COOKIE" in capsys.readouterr().out


def test_config_file_remains_authoritative_when_env_is_also_set(monkeypatch):
    cfg = Config()
    cfg.set("xueqiu_cookie", "xq_a_token=FILE-secret")
    monkeypatch.setenv("XUEQIU_COOKIE", "xq_a_token=ENV-secret")
    monkeypatch.setattr(xq._opener, "open", lambda *_a, **_k: pytest.fail("fallback"))
    xq._ensure_cookies(cfg)
    assert xq._cookie_source == "file"
    assert [c.value for c in xq._cookie_jar] == ["FILE-secret"]


@pytest.mark.parametrize(
    "extra",
    [
        ["groq-key"],
        ["proxy", "secret"],
        ["--stdin"],
        ["--from-browser", "chrome", "--platform", "xueqiu"],
        ["--platform", "xueqiu"],
        ["--profile", "Profile 1"],
        ["--sync-legacy-twitter"],
    ],
)
def test_unset_conflicts_fail_before_config_access(monkeypatch, extra):
    monkeypatch.setattr("agent_reach.config.Config", lambda: pytest.fail("configuration accessed"))
    with pytest.raises(SystemExit) as exc:
        run_cli(monkeypatch, "--unset", "xueqiu-cookie", *extra)
    assert exc.value.code == 2


def test_unset_does_not_accept_arbitrary_keys(monkeypatch):
    with pytest.raises(SystemExit) as exc:
        run_cli(monkeypatch, "--unset", "github-token")
    assert exc.value.code == 2


def test_unset_failed_replace_preserves_file_and_does_not_claim_success(monkeypatch, capsys):
    cfg = Config()
    cfg.set("xueqiu_cookie", "xq_a_token=SECRET-cookie")
    before = cfg.config_path.read_bytes()

    def fail_replace(*_args):
        raise PermissionError("SECRET-error")

    monkeypatch.setattr("agent_reach.config.os.replace", fail_replace)
    with pytest.raises(SystemExit) as exc:
        run_cli(monkeypatch, "--unset", "xueqiu-cookie")
    assert exc.value.code == 1
    assert cfg.config_path.read_bytes() == before
    assert list(cfg.config_dir.glob(".config.yaml.*.tmp")) == []
    output = capsys.readouterr()
    assert "Removed" not in output.out
    assert "SECRET" not in output.out + output.err


def test_unset_rejects_malformed_yaml_without_echoing_it(monkeypatch, capsys):
    cfg = Config()
    cfg.set("xueqiu_cookie", "temporary")
    cfg.config_path.write_text("xueqiu_cookie: [SECRET-invalid\n", encoding="utf-8")
    before = cfg.config_path.read_bytes()
    with pytest.raises(SystemExit) as exc:
        run_cli(monkeypatch, "--unset", "xueqiu-cookie")
    assert exc.value.code == 1
    assert cfg.config_path.read_bytes() == before
    output = capsys.readouterr()
    assert "SECRET" not in output.out + output.err


def test_unset_refuses_invalid_utf8_without_changing_file(monkeypatch, capsys):
    cfg = Config()
    cfg.set("xueqiu_cookie", "temporary")
    cfg.config_path.write_bytes(b"xueqiu_cookie: SECRET-\xff")
    before = cfg.config_path.read_bytes()
    with pytest.raises(SystemExit) as exc:
        run_cli(monkeypatch, "--unset", "xueqiu-cookie")
    assert exc.value.code == 1
    assert cfg.config_path.read_bytes() == before
    output = capsys.readouterr()
    assert "SECRET" not in output.out + output.err


def test_unset_refuses_symlinked_config(monkeypatch, tmp_path, capsys):
    cfg = Config()
    cfg.config_dir.mkdir(parents=True)
    victim = tmp_path / "victim.yaml"
    victim.write_text("xueqiu_cookie: SECRET-cookie\n", encoding="utf-8")
    before = victim.read_bytes()
    try:
        cfg.config_path.symlink_to(victim)
    except OSError:
        pytest.skip("symlink creation unavailable")
    with pytest.raises(SystemExit) as exc:
        run_cli(monkeypatch, "--unset", "xueqiu-cookie")
    assert exc.value.code == 1
    assert victim.read_bytes() == before and cfg.config_path.is_symlink()
    output = capsys.readouterr()
    assert "SECRET" not in output.out + output.err


def test_unset_security_rejection_never_claims_success(monkeypatch, capsys):
    from agent_reach.config import ConfigSecurityError

    def refuse():
        raise ConfigSecurityError("SECRET-path")

    monkeypatch.setattr("agent_reach.config.Config", refuse)
    with pytest.raises(SystemExit) as exc:
        run_cli(monkeypatch, "--unset", "xueqiu-cookie")
    assert exc.value.code == 1
    output = capsys.readouterr()
    assert "SECRET" not in output.out + output.err
    assert "Removed" not in output.out


def response(payload):
    return io.BytesIO(json.dumps(payload).encode("utf-8"))


@pytest.mark.parametrize("source", ["file", "env"])
@pytest.mark.parametrize("transport", ["http", "json"])
def test_rejection_explains_actual_source_and_recovery(monkeypatch, source, transport):
    cfg = Config()
    if source == "file":
        cfg.set("xueqiu_cookie", "xq_a_token=SECRET-cookie")
    else:
        monkeypatch.setenv("XUEQIU_COOKIE", "xq_a_token=SECRET-cookie")
    payload = {"error_code": "400016", "error_description": "SECRET-response"}
    calls = []

    def open_request(req, **_kwargs):
        calls.append(req.full_url)
        if transport == "http":
            raise HTTPError(req.full_url, 400, "SECRET-reason", {}, response(payload))
        return response(payload)

    monkeypatch.setattr(xq._opener, "open", open_request)
    channel = xq.XueqiuChannel()
    channel.active_backend = channel.backends[0]
    status, message = channel.check(cfg)
    assert status == "warn"
    assert "400016" in message and "可能" in message
    assert "SECRET" not in message
    assert len(calls) == 1  # No implicit identity switch or retry.
    if source == "file":
        assert "agent-reach configure --unset xueqiu-cookie" in message
        assert "config.yaml" in message
        assert cfg.get("xueqiu_cookie") == "xq_a_token=SECRET-cookie"
    else:
        assert "XUEQIU_COOKIE" in message
        assert "--unset" not in message
    assert channel.active_backend is None


def test_anonymous_rejection_is_not_diagnosed_as_saved_cookie_expiry(monkeypatch):
    calls = []

    def open_request(req, **_kwargs):
        calls.append(req.full_url)
        if len(calls) == 1:
            return response({})
        raise HTTPError(req.full_url, 400, "bad", {}, response({"error_code": 400016}))

    monkeypatch.setattr(xq._opener, "open", open_request)
    _, message = xq.XueqiuChannel().check(Config())
    assert "400016" in message and "匿名" in message
    assert "--unset" not in message


def test_http_error_other_than_400_preserves_body_for_callers(monkeypatch):
    cfg = Config()
    cfg.set("xueqiu_cookie", "xq_a_token=SECRET-cookie")
    error = HTTPError("https://xueqiu.com", 429, "limit", {}, io.BytesIO(b"retry later"))
    monkeypatch.setattr(xq._opener, "open", lambda *_a, **_k: (_ for _ in ()).throw(error))
    with pytest.raises(HTTPError) as exc:
        xq._get_json("https://xueqiu.com/test", cfg)
    assert exc.value is error and exc.value.read() == b"retry later"


@pytest.mark.parametrize(
    "body",
    [b'{"error_code":123}', b'{"error_code":400016}', b"not-json", b"\xff", b"[]", b"x" * 5000],
    ids=["other-code", "session-code", "invalid-json", "invalid-utf8", "array", "oversized"],
)
def test_data_requests_preserve_http_400_without_inspecting_body(monkeypatch, body):
    cfg = Config()
    cfg.set("xueqiu_cookie", "xq_a_token=SECRET-cookie")
    reads = []

    class NonSeekableBody(io.BytesIO):
        def read(self, size=-1):
            reads.append(size)
            return super().read(size)

        def seek(self, *_args):
            pytest.fail("HTTP response bodies cannot be assumed seekable")

    stream = NonSeekableBody(body)
    error = HTTPError("https://xueqiu.com", 400, "bad", {}, stream)
    monkeypatch.setattr(xq._opener, "open", lambda *_a, **_k: (_ for _ in ()).throw(error))
    with pytest.raises(HTTPError) as exc:
        xq._get_json("https://xueqiu.com/test", cfg)
    assert exc.value is error
    assert reads == [] and not stream.closed
    assert exc.value.read() == body
    exc.value.close()


@pytest.mark.parametrize(
    "failure",
    [
        HTTPError("https://xueqiu.com", 400, "bad", {}, response({"error_code": 123})),
        HTTPError("https://xueqiu.com", 403, "bad", {}, response({"error_code": 400016})),
        URLError("SECRET-network"),
        json.JSONDecodeError("SECRET-json", "", 0),
    ],
)
def test_unrelated_failures_are_not_misdiagnosed_or_leaked(monkeypatch, failure):
    monkeypatch.setattr(xq, "_get_json", lambda *_a: (_ for _ in ()).throw(failure))
    _, message = xq.XueqiuChannel().check()
    assert "--unset" not in message
    assert "SECRET" not in message
    assert "可能已过期" not in message


@pytest.mark.parametrize(
    "body",
    [b"not-json", b"\xff", b"[]", b"x" * 5000],
    ids=["invalid-json", "invalid-utf8", "array", "oversized"],
)
def test_http_error_body_is_bounded_and_not_echoed(monkeypatch, body):
    reads = []

    class Body(io.BytesIO):
        def read(self, size=-1):
            reads.append(size)
            assert 0 < size <= 4097
            return super().read(size)

    error = HTTPError("https://xueqiu.com", 400, "SECRET-reason", {}, Body(body))
    monkeypatch.setattr(xq._opener, "open", lambda *_a, **_k: (_ for _ in ()).throw(error))
    cfg = Config()
    cfg.set("xueqiu_cookie", "xq_a_token=SECRET-cookie")
    _, message = xq.XueqiuChannel().check(cfg)
    assert reads == [4097]
    assert "SECRET" not in message and "--unset" not in message


@pytest.mark.parametrize("code", [400, 403, 429])
def test_health_check_closes_owned_http_errors_without_probing_other_statuses(monkeypatch, code):
    reads = []

    class Body(io.BytesIO):
        def read(self, size=-1):
            reads.append(size)
            return super().read(size)

    body = Body(b'{"error_code":123}')
    error = HTTPError("https://xueqiu.com", code, "SECRET-reason", {}, body)
    monkeypatch.setattr(xq, "_get_json", lambda *_a: (_ for _ in ()).throw(error))
    status, message = xq.XueqiuChannel().check()
    assert status == "warn" and "SECRET" not in message
    assert body.closed
    assert reads == ([4097] if code == 400 else [])


@pytest.mark.parametrize("body", [b'{"error_code":123}', b'{"error_code":400016}', b"x" * 5000])
def test_real_http_400_remains_readable_by_data_callers(monkeypatch, body):
    """Use a real socket-backed, non-seekable urllib error response."""

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(400)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True
    )
    monkeypatch.setattr(xq, "_ensure_cookies", lambda *_a: None)
    thread.start()
    try:
        with pytest.raises(HTTPError) as exc:
            xq._get_json(f"http://127.0.0.1:{server.server_port}/quote")
        with exc.value as error:
            assert error.code == 400
            assert error.read() == body
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_real_cli_subprocess_clears_saved_key_then_is_idempotent(tmp_path):
    home = tmp_path / "process-home"
    directory = home / ".agent-reach"
    directory.mkdir(parents=True)
    path = directory / "config.yaml"
    path.write_text("xueqiu_cookie: 'xq_a_token=SECRET-cookie'\nother: 保留\n", encoding="utf-8")
    env = dict(os.environ, HOME=str(home), USERPROFILE=str(home), PYTHONUTF8="1")
    env.pop("XUEQIU_COOKIE", None)
    env.pop("PYTEST_CURRENT_TEST", None)
    command = [sys.executable, "-m", "agent_reach.cli", "configure", "--unset", "xueqiu-cookie"]
    for _ in range(2):
        proc = subprocess.run(command, env=env, capture_output=True, encoding="utf-8", timeout=10)
        assert proc.returncode == 0, proc.stderr
        assert "SECRET" not in proc.stdout + proc.stderr
    assert yaml.safe_load(path.read_text(encoding="utf-8")) == {"other": "保留"}


def test_docs_explain_limits_of_clear_and_anonymous_recovery():
    root = Path(__file__).resolve().parents[1]
    for file in ["docs/troubleshooting.md", "agent_reach/skill/references/finance.md"]:
        text = (root / file).read_text(encoding="utf-8")
        assert "agent-reach configure --unset xueqiu-cookie" in text
        assert "XUEQIU_COOKIE" in text
        assert "新进程" in text
        assert "匿名" in text


def test_real_http_and_fresh_process_recovery_without_real_credentials(tmp_path):
    """Exercise urllib HTTPError parsing, CLI persistence and a new session.

    The loopback service deliberately rejects requests without its public
    fixture cookie. It is not a test of Xueqiu's live authentication policy.
    """
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append(self.path)
            if self.path == "/session":
                self.send_response(200)
                self.send_header("Set-Cookie", "public_fixture=ok; Path=/")
                payload = {}
            elif "public_fixture=ok" in self.headers.get("Cookie", ""):
                self.send_response(200)
                payload = {"data": {"quote": {"symbol": "TEST", "current": 1}}}
            else:
                self.send_response(400)
                payload = {"error_code": 400016, "error_description": "SECRET-server"}
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(payload).encode("utf-8"))

        def log_message(self, *_args):
            pass

    home = tmp_path / "http-home"
    directory = home / ".agent-reach"
    directory.mkdir(parents=True)
    path = directory / "config.yaml"
    path.write_text("xueqiu_cookie: 'xq_a_token=SECRET-fixture'\nkeep: 42\n", encoding="utf-8")
    env = dict(os.environ, HOME=str(home), USERPROFILE=str(home), PYTHONUTF8="1")
    env.pop("XUEQIU_COOKIE", None)
    env.pop("PYTEST_CURRENT_TEST", None)
    worker = """
import sys
from agent_reach.channels import xueqiu as xq
from agent_reach.config import Config
for name in ('_XUEQIU_HOME', '_XUEQIU_SESSION_URL'):
    if hasattr(xq, name):
        setattr(xq, name, sys.argv[1] + '/session')
get_json = xq._get_json
xq._get_json = lambda url, config=None: get_json(sys.argv[1] + '/quote', config)
status, message = xq.XueqiuChannel().check(Config(read_only=True))
if status != 'ok':
    print(message)
    raise SystemExit(3)
print(status)
"""
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True
    )
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_port}"
        command = [sys.executable, "-c", worker, base]
        before = subprocess.run(command, env=env, capture_output=True, encoding="utf-8", timeout=10)
        assert before.returncode == 3
        assert "--unset xueqiu-cookie" in before.stdout
        assert requests == ["/quote"]
        clear = subprocess.run(
            [sys.executable, "-m", "agent_reach.cli", "configure", "--unset", "xueqiu-cookie"],
            env=env,
            capture_output=True,
            encoding="utf-8",
            timeout=10,
        )
        assert clear.returncode == 0
        assert yaml.safe_load(path.read_text(encoding="utf-8")) == {"keep": 42}
        after = subprocess.run(command, env=env, capture_output=True, encoding="utf-8", timeout=10)
        assert after.returncode == 0 and after.stdout.strip() == "ok"
        assert requests == ["/quote", "/session", "/quote"]
        assert (
            "SECRET"
            not in before.stdout
            + before.stderr
            + clear.stdout
            + clear.stderr
            + after.stdout
            + after.stderr
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
