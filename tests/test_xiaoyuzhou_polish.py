"""Run the shipped polish Python block against a local HTTP API.

No real Groq credentials or live provider requests are used. Windows argv
conversion cannot be reproduced on POSIX; the multipart test verifies the
file-backed UTF-8 transport which avoids that conversion.
"""

import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from test_xiaoyuzhou_install import (
    ROOT,
    TRANSCRIBE_SCRIPT,
    _append_bash_function,
    _bash_path,
    _script_env,
)


@pytest.fixture
def local_api():
    state = {
        "requests": [],
        "multipart": [],
        "respond": lambda text, _n: (200, text + "。", "stop"),
    }

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            raw = self.rfile.read(int(self.headers["Content-Length"]))
            if self.path.endswith("/audio/transcriptions"):
                state["multipart"].append(raw)
                self.send_response(200)
                self.end_headers()
                self.wfile.write("原文内容".encode("utf-8"))
                return
            request = json.loads(raw)
            state["requests"].append(request)
            text = request["messages"][0]["content"].split("原文：\n", 1)[1]
            status, content, finish = state["respond"](text, len(state["requests"]))
            self.send_response(status)
            self.send_header("Retry-After", "0")
            self.end_headers()
            response = {"choices": [{"message": {"content": content}, "finish_reason": finish}]}
            self.wfile.write(json.dumps(response, ensure_ascii=False).encode("utf-8"))

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    state["url"] = f"http://127.0.0.1:{server.server_port}"
    try:
        yield state
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def _api_redirect(tmp_path, local_api):
    """Redirect only the test child's urllib Groq requests to a real local server."""
    hook = tmp_path / "hooks"
    hook.mkdir()
    (hook / "sitecustomize.py").write_text(
        """
import os
import urllib.request
_real_open = urllib.request.urlopen
def local_open(request, *args, **kwargs):
    if isinstance(request, urllib.request.Request) and request.full_url.startswith("https://api.groq.com/"):
        request = urllib.request.Request(
            request.full_url.replace("https://api.groq.com", os.environ["TEST_API"], 1),
            data=request.data, headers=dict(request.header_items()), method=request.get_method())
    return _real_open(request, *args, **kwargs)
urllib.request.urlopen = local_open
""",
        encoding="utf-8",
    )
    return {"TEST_API": local_api["url"], "PYTHONPATH": str(hook)}


def _run_polish(tmp_path, local_api, text="原文内容", model=None):
    source = TRANSCRIBE_SCRIPT.read_text(encoding="utf-8")
    start = source.index("import json, os, sys")
    block = source[start : source.index("\nPY", start)]
    runner = tmp_path / "polish.py"
    runner.write_text(block, encoding="utf-8")
    original = tmp_path / "original.txt"
    original.write_text(text, encoding="utf-8")
    output = tmp_path / "polished.txt"
    env = os.environ.copy()
    env.update(_api_redirect(tmp_path, local_api))
    env.update(
        {
            "IN_FILE": str(original),
            "OUT_FILE": str(output),
            "GROQ_API_KEY": "test-only-key",
            "POLISH_MODEL": model or "qwen/qwen3.8-27b",
            "PYTHONUTF8": "1",
            "PYTHONIOENCODING": "utf-8",
        }
    )
    result = subprocess.run(
        [sys.executable, str(runner)], env=env, capture_output=True, encoding="utf-8", timeout=15
    )
    return result, output.read_text(encoding="utf-8").strip()


@pytest.mark.parametrize("mode", ["empty", "rewrite", "truncated", "unavailable"])
def test_polish_preserves_content_when_provider_cannot_safely_polish(tmp_path, local_api, mode):
    cases = {
        "empty": (200, "", "length"),
        "rewrite": (200, "改写了原文", "stop"),
        "truncated": (200, "原", "length"),
        "unavailable": (404, "", "stop"),
    }
    local_api["respond"] = lambda _text, _n: cases[mode]
    result, output = _run_polish(tmp_path, local_api)
    assert output == "原文内容"
    assert result.returncode == 2
    assert "⚠️" in result.stdout
    assert "✅" not in result.stdout
    if mode == "empty":
        assert len(local_api["requests"]) == 1


def test_polish_splits_long_input_and_bounds_completion_budget(tmp_path, local_api):
    result, output = _run_polish(tmp_path, local_api, text="正文" * 1100)
    assert result.returncode == 0
    assert output.replace("。", "") == "正文" * 1100
    requests = local_api["requests"]
    assert len(requests) == 3
    assert all(r["model"] == "qwen/qwen3.8-27b" for r in requests)
    assert all(r["reasoning_effort"] == "none" for r in requests)
    assert all(r["max_completion_tokens"] <= 3000 for r in requests)


def test_polish_retries_rate_limit_then_returns_verified_result(tmp_path, local_api):
    local_api["respond"] = lambda text, n: (
        (429, "", "stop") if n == 1 else (200, text + "。", "stop")
    )
    result, output = _run_polish(tmp_path, local_api)
    assert result.returncode == 0
    assert output == "原文内容。"
    assert len(local_api["requests"]) == 2


def test_polish_413_splits_without_losing_words(tmp_path, local_api):
    local_api["respond"] = lambda text, _n: (
        (413, "", "stop") if len(text) > 100 else (200, text + "。", "stop")
    )
    result, output = _run_polish(tmp_path, local_api, text="正文" * 100)
    assert result.returncode == 0
    assert output.replace("。", "") == "正文" * 100
    assert len(local_api["requests"]) == 3


def test_polish_honors_explicit_model_override(tmp_path, local_api):
    result, output = _run_polish(tmp_path, local_api, model="explicit-user-model")
    assert result.returncode == 0
    assert output == "原文内容。"
    assert local_api["requests"][0]["model"] == "explicit-user-model"
    assert "reasoning_effort" not in local_api["requests"][0]


@pytest.mark.parametrize("provider_available", [False, True])
def test_full_script_sends_utf8_file_field_and_reports_polish_status(
    tmp_path, local_api, bash_executable, provider_available
):
    if not provider_available:
        local_api["respond"] = lambda _text, _n: (404, "", "stop")
    env, curl_log, temp_root, bash_env = _script_env(
        tmp_path,
        """
case "$*" in
  *audio/transcriptions*)
    printf '%s\\n' "$@" >> "$CURL_LOG"
    args=()
    for arg in "$@"; do
      if [ "$arg" = "https://api.groq.com/openai/v1/audio/transcriptions" ]; then
        args+=("$TEST_API/openai/v1/audio/transcriptions")
      else args+=("$arg"); fi
    done
    command curl "${args[@]}" ;;
  *media.xyzcdn.net*)
    while [ "$#" -gt 0 ]; do
      if [ "$1" = "-o" ]; then printf x > "$2"; return 0; fi
      shift
    done ;;
  *) printf '%s' '{"title":"测试","url":"https://media.xyzcdn.net/audio.m4a"}' ;;
esac
""",
    )
    _append_bash_function(bash_env, "ffprobe", "printf '10\\n'")
    _append_bash_function(
        bash_env, "ffmpeg", 'for output in "$@"; do :; done; printf x > "$output"'
    )
    env.update(_api_redirect(tmp_path, local_api))
    env.update({"PYTHONIOENCODING": "cp1252", "PYTHONUTF8": "0"})
    output = tmp_path / "out.md"
    result = subprocess.run(
        [
            bash_executable,
            str(TRANSCRIBE_SCRIPT),
            "--polish",
            "https://www.xiaoyuzhoufm.com/episode/test",
            _bash_path(output),
        ],
        env=env,
        cwd=ROOT,
        capture_output=True,
        encoding="utf-8",
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    assert "原文内容" in output.read_text(encoding="utf-8")
    assert ("部分未完成，保留原文" in output.read_text(encoding="utf-8")) is (
        not provider_available
    )
    if not provider_available:
        assert "⚠️" in result.stdout
    assert "prompt=<" in curl_log.read_text(encoding="utf-8")
    assert "以下是一段" not in curl_log.read_text(encoding="utf-8")
    assert "以下是一段中文普通话播客录音".encode("utf-8") in local_api["multipart"][0]
    assert b'name="prompt"; filename=' not in local_api["multipart"][0]
    assert list(temp_root.glob("agent-reach-xiaoyuzhou.*")) == []
