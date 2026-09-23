"""NGA export correctness: identity filtering, pagination, interruption and resume."""

import copy
import json
import subprocess

import pytest

from agent_reach.channels import get_channel
from agent_reach.channels.nga import NGABrowser, thread_url, validate_page
from agent_reach.cli import main
from agent_reach.nga_export import export_thread, task_lock, to_markdown

URL = "https://bbs.nga.cn/read.php?tid=123"


def post(pid, uid="42", floor=0):
    return dict(pid=str(pid), floor=floor, author="同名用户", author_uid=uid,
                created_at="2026-09-23 12:00", text="正文\n第二行", images=[], links=[],
                url=f"{URL}#pid{pid}Anchor", edited="", content_present=True)


def page(number, posts):
    return dict(url=thread_url(URL, number), tid="123", page=number, total_pages=3,
                title="测试主题", posts=posts)


class Reader:
    def __init__(self, fail=None):
        self.calls = []
        self.closed = False
        self.fail = fail
        self.pages = {1: page(1, [post(0), post(11, "43", 1)]),
                      2: page(2, [post(22, "43", 20)]),  # No OP replies.
                      3: page(3, [post(33, "42", 40)])}

    def read_page(self, url):
        number = int(url.rsplit("=", 1)[1])
        self.calls.append(number)
        if number == self.fail:
            raise RuntimeError("browser disconnected")
        return copy.deepcopy(self.pages[number])

    def close(self):
        self.closed = True


@pytest.mark.parametrize("url", [
    "https://bbs.nga.cn.evil.test/read.php?tid=123", "https://evil.test/read.php?tid=123",
    "file:///read.php?tid=123", "https://name:secret@bbs.nga.cn/read.php?tid=123",
    URL + "&tid=456", URL + "&page=0", URL + "&authorid=42", URL + "&page=-1",
    "https://bbs.nga.cn/post.php?tid=123", "https://bbs.nga.cn:999/read.php?tid=123",
])
def test_reject_unsafe_or_filtered_url(url):
    with pytest.raises(ValueError):
        thread_url(url)
    assert not get_channel("nga").can_handle(url)


def test_registry_and_page_link():
    assert get_channel("nga").can_handle(URL)
    assert thread_url(URL + "&page=2#pid22Anchor").endswith("&page=2")


def test_only_author_uses_uid_and_counts_empty_filtered_page(tmp_path):
    reader = Reader()
    result = export_thread(URL, directory=tmp_path, all_pages=True, only_author=True,
                           browser=reader, interval=0)
    assert reader.calls == [1, 2, 3]
    assert reader.closed
    assert [p["pid"] for p in result["posts"]] == ["0", "33"]
    assert result["pages_read"] == [1, 2, 3]
    assert result["complete"] is True
    assert len(json.loads((tmp_path / "state.json").read_text())["pages"]["2"]["posts"]) == 1
    assert (tmp_path / "export.md").exists()


def test_start_page_metadata_not_exported(tmp_path):
    reader = Reader()
    result = export_thread(URL, directory=tmp_path, start_page=3, only_author=True,
                           browser=reader, interval=0)
    assert reader.calls == [1, 3]
    assert result["pages_read"] == [3]
    assert [p["pid"] for p in result["posts"]] == ["33"]


def test_url_page_is_default_start(tmp_path):
    reader = Reader()
    result = export_thread(URL + "&page=2", directory=tmp_path, browser=reader, interval=0)
    assert reader.calls == [1, 2]
    assert result["start_page"] == result["end_page"] == 2


def test_failure_preserves_pages_and_resumes_without_refetch(tmp_path):
    broken = Reader(fail=3)
    with pytest.raises(RuntimeError):
        export_thread(URL, directory=tmp_path, all_pages=True, only_author=True,
                      browser=broken, interval=0)
    state = json.loads((tmp_path / "state.json").read_text())
    assert set(state["pages"]) == {"1", "2"}
    assert state["last_error"]["page"] == 3
    assert broken.closed
    reader = Reader()
    result = export_thread(directory=tmp_path, resume=True, browser=reader, interval=0)
    assert reader.calls == [3]
    assert result["complete"]
    assert [p["pid"] for p in result["posts"]] == ["0", "33"]


def test_budget_and_finished_resume(tmp_path):
    result = export_thread(URL, directory=tmp_path, all_pages=True, max_pages=1,
                           browser=Reader(), interval=0)
    assert not result["complete"] and result["next_page"] == 2
    assert "未完成" in to_markdown(result)
    export_thread(directory=tmp_path, resume=True, browser=Reader(), interval=0)
    reader = Reader()
    result = export_thread(directory=tmp_path, resume=True, browser=reader, interval=0)
    assert reader.calls == [] and result["complete"]


def test_repeated_page_is_not_saved(tmp_path):
    reader = Reader()
    reader.pages[2]["posts"] = reader.pages[1]["posts"]
    with pytest.raises(ValueError, match="重复"):
        export_thread(URL, directory=tmp_path, all_pages=True, browser=reader, interval=0)
    assert set(json.loads((tmp_path / "state.json").read_text())["pages"]) == {"1"}


def test_deduplicate_pinned_post(tmp_path):
    reader = Reader()
    reader.pages[2]["posts"].insert(0, post(0))
    result = export_thread(URL, directory=tmp_path, all_pages=True, browser=reader, interval=0)
    assert [p["pid"] for p in result["posts"]].count("0") == 1


@pytest.mark.parametrize("change", [
    {"url": "https://bbs.nga.cn/login.php"}, {"posts": []}, {"page": 2},
    {"posts": [{**post(0), "content_present": False}]},
])
def test_bad_page_never_counts_as_success(change):
    with pytest.raises(ValueError):
        validate_page({**page(1, [post(0)]), **change}, URL)


def test_resume_refuses_changed_filter_and_corrupt_checkpoint(tmp_path):
    export_thread(URL, directory=tmp_path, browser=Reader(), interval=0)
    with pytest.raises(ValueError, match="不能更改"):
        export_thread(directory=tmp_path, resume=True, only_author=True)
    state_path = tmp_path / "state.json"
    state = json.loads(state_path.read_text())
    state["pages"]["1"]["url"] = "https://evil.test/"
    state_path.write_text(json.dumps(state))
    with pytest.raises(ValueError):
        export_thread(directory=tmp_path, resume=True, browser=Reader())


def test_task_lock_released_after_failure(tmp_path):
    with task_lock(tmp_path):
        with pytest.raises(ValueError, match="正在运行"):
            with task_lock(tmp_path):
                pass
    with task_lock(tmp_path):
        pass


def test_opencli_public_commands_and_cleanup(monkeypatch):
    calls = []
    monkeypatch.setattr("shutil.which", lambda _: "/bin/opencli")
    monkeypatch.setenv("OPENCLI_DAEMON_PORT", "old-value")

    def run(cmd, **kwargs):
        calls.append(cmd)
        assert "OPENCLI_DAEMON_PORT" not in kwargs["env"]
        return subprocess.CompletedProcess(cmd, 0, json.dumps(page(1, [post(0)])), "")

    monkeypatch.setattr("subprocess.run", run)
    browser = NGABrowser(profile="personal")
    browser.read_page(URL)
    browser.close()
    assert all(cmd[1:4] == ["--profile", "personal", "browser"] for cmd in calls)
    assert len({cmd[4] for cmd in calls}) == 1
    assert [cmd[5] for cmd in calls] == ["open", "wait", "eval", "close"]


def test_cli_json_stdout_and_incomplete_exit(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr("agent_reach.nga_export.NGABrowser", lambda **_: Reader())
    monkeypatch.setattr("sys.argv", ["agent-reach", "nga", "read", URL, "--all-pages",
                                   "--max-pages", "1", "--state-dir", str(tmp_path),
                                   "--format", "json"])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 3
    captured = capsys.readouterr()
    assert json.loads(captured.out)["next_page"] == 2
    assert "续传" in captured.err


def test_markdown_preserves_text_without_active_html(tmp_path):
    reader = Reader()
    reader.pages[1]["posts"][0]["text"] = '<script>alert(1)</script>\n![x](file:///secret)'
    reader.pages[1]["posts"][0]["images"] = [{"url": "https://img.nga.cn/photo.jpg", "alt": "图"}]
    result = export_thread(URL, directory=tmp_path, browser=reader)
    md = to_markdown(result)
    assert "<script>" not in md and "&lt;script&gt;" in md
    assert "[图片：图](<https://img.nga.cn/photo.jpg>)" in md


def test_cli_cannot_overwrite_checkpoint(monkeypatch, tmp_path):
    original = '{"do_not_overwrite": true}'
    (tmp_path / "state.json").write_text(original)
    monkeypatch.setattr("sys.argv", ["agent-reach", "nga", "read", "--resume", str(tmp_path),
                                   "-o", str(tmp_path / "state.json")])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1
    assert (tmp_path / "state.json").read_text() == original


@pytest.mark.parametrize("options", [
    {"start_page": 0}, {"start_page": 3, "end_page": 2},
    {"all_pages": True, "end_page": 2}, {"start_page": 4}, {"max_pages": 0},
])
def test_invalid_ranges(tmp_path, options):
    with pytest.raises(ValueError):
        export_thread(URL, directory=tmp_path, browser=Reader(), **options)
