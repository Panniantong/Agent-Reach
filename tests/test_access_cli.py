import json
import subprocess
from unittest.mock import patch

from agent_reach.access import AccessRouter
from agent_reach.cli import main


def _run(argv, capsys):
    with patch("sys.argv", ["agent-reach", *argv]):
        main()
    return json.loads(capsys.readouterr().out)


def test_read_returns_normalized_json(capsys):
    with patch("agent_reach.access.AccessRouter.read", return_value={
        "platform": "web", "backend": "Jina Reader", "content": "hello"
    }):
        result = _run(["read", "https://example.com", "--json"], capsys)

    assert result["status"] == "success"
    assert result["source_url"] == "https://example.com"
    assert result["platform"] == "web"
    assert result["backend"] == "Jina Reader"
    assert result["content"] == "hello"
    assert result["author"] is None
    assert result["replies"] == []
    assert result["media"] == []
    assert result["limitations"] == []
    assert result["retrieved_at"].endswith("Z")


def test_extract_is_an_alias_with_the_same_normalized_contract(capsys):
    with patch("agent_reach.access.AccessRouter.extract", return_value={
        "platform": "twitter", "backend": "twitter-cli", "content": {"id": "1"}
    }):
        result = _run(["extract", "https://x.com/a/status/1", "--json"], capsys)
    assert result["status"] == "success"
    assert result["platform"] == "twitter"
    assert result["content"] == {"id": "1"}


def test_normalizer_promotes_backend_metadata():
    from agent_reach.access import normalize_result

    result = normalize_result(
        {
            "platform": "twitter",
            "backend": "twitter-cli",
            "content": {
                "full_text": "hello",
                "author": {"username": "philipp"},
                "created_at": "2026-07-12T00:00:00Z",
                "replies": [{"id": "2"}],
                "media": [{"url": "https://example.com/image.jpg"}],
            },
        },
        source_url="https://x.com/philipp/status/1",
    )

    assert result["content"] == "hello"
    assert result["author"] == {"username": "philipp"}
    assert result["published_at"] == "2026-07-12T00:00:00Z"
    assert result["replies"] == [{"id": "2"}]
    assert result["media"] == [{"url": "https://example.com/image.jpg"}]

    github = normalize_result(
        {"platform": "github", "backend": "gh CLI", "content": {"createdAt": "now"}}
    )
    assert github["published_at"] == "now"


def test_search_returns_normalized_json(capsys):
    with patch("agent_reach.access.AccessRouter.search", return_value={
        "platform": "exa_search", "backend": "Exa via mcporter", "content": [{"title": "A"}]
    }):
        result = _run(["search", "agent infrastructure", "--json"], capsys)
    assert result["status"] == "success"
    assert result["query"] == "agent infrastructure"
    assert result["content"] == [{"title": "A"}]


def test_backend_error_is_machine_readable(capsys):
    with patch("agent_reach.access.AccessRouter.read", side_effect=RuntimeError("network blocked")):
        result = _run(["read", "https://example.com", "--json"], capsys)
    assert result["status"] == "error"
    assert result["limitations"] == ["network blocked"]


def test_search_routes_to_exa_without_shell_interpolation():
    completed = subprocess.CompletedProcess(
        [], 0, json.dumps({"results": [{"title": "A"}]}), ""
    )
    with patch("agent_reach.access.subprocess.run", return_value=completed) as run, patch(
        "agent_reach.access.get_channel"
    ) as get_channel:
        get_channel.return_value.check.return_value = ("ok", "ready")
        result = AccessRouter().search('a "quoted" query', limit=3)

    command = run.call_args.args[0]
    assert command[:2] == ["mcporter", "call"]
    assert 'query: "a \\"quoted\\" query"' in command[2]
    assert "numResults: 3" in command[2]
    assert result["content"] == {"results": [{"title": "A"}]}


def test_search_falls_back_to_jina_when_mcporter_is_missing():
    with patch("agent_reach.access._run", side_effect=FileNotFoundError("mcporter")), patch(
        "agent_reach.access._jina_search", return_value="fallback results"
    ):
        result = AccessRouter().search("agent infrastructure", limit=4)

    assert result == {
        "platform": "web_search",
        "backend": "DuckDuckGo via Jina Reader",
        "content": "fallback results",
        "limitations": [
            "Exa via mcporter unavailable; used DuckDuckGo via Jina Reader"
        ],
    }


def test_search_checks_exa_health_before_execution():
    router = AccessRouter()
    with patch("agent_reach.access.get_channel") as get_channel, patch(
        "agent_reach.access._run"
    ) as run, patch("agent_reach.access._jina_search", return_value="fallback"):
        get_channel.return_value.check.return_value = ("off", "not configured")
        get_channel.return_value.active_backend = None
        result = router.search("query")

    run.assert_not_called()
    assert result["backend"] == "DuckDuckGo via Jina Reader"


def test_github_issue_uses_issue_command_and_blob_uses_web_fallback():
    from agent_reach.channels.github import GitHubChannel

    channel = GitHubChannel()
    channel.active_backend = "gh CLI"
    assert channel.read_command("https://github.com/acme/repo/issues/42") == [
        "gh", "issue", "view", "42", "--repo", "acme/repo", "--json",
        "number,title,body,author,createdAt,url,comments",
    ]
    assert channel.read_command("https://github.com/acme/repo/blob/main/README.md") is None


def test_read_falls_back_to_jina_after_selected_backend_fails():
    class ChannelStub:
        name = "github"
        active_backend = "gh CLI"

        def can_handle(self, url):
            return True

        def check(self, config):
            return "warn", "gh unauthenticated"

        def read_command(self, url):
            return ["gh", "issue", "view", "1"]

    with patch("agent_reach.access.get_all_channels", return_value=[ChannelStub()]), patch(
        "agent_reach.access._run", side_effect=RuntimeError("auth failed")
    ), patch("agent_reach.channels.web.WebChannel.read", return_value="web fallback"):
        result = AccessRouter().read("https://github.com/acme/repo/issues/1")

    assert result["backend"] == "Jina Reader fallback"
    assert result["content"] == "web fallback"


def test_youtube_extract_returns_clean_subtitle_text(tmp_path):
    class YouTubeStub:
        name = "youtube"
        active_backend = "yt-dlp"

        def can_handle(self, url):
            return True

        def check(self, config):
            return "ok", "ready"

        def extract_content(self, url, run_command):
            from agent_reach.channels.youtube import YouTubeChannel

            return YouTubeChannel().extract_content(url, run_command)

    def fake_run(command, timeout=60):
        if "--dump-single-json" in command:
            return {
                "id": "video",
                "original_language": "th",
                "automatic_captions": {"th": [{"url": "https://example.com/sub"}]},
            }
        output_template = command[command.index("-o") + 1]
        subtitle = output_template.replace("%(id)s", "video") + ".en.vtt"
        with open(subtitle, "w", encoding="utf-8") as handle:
            handle.write("WEBVTT\n\n00:00.000 --> 00:01.000\nHello\nHello\n\nWorld\n")
        return ""

    with patch("agent_reach.access.get_all_channels", return_value=[YouTubeStub()]), patch(
        "agent_reach.access._run", side_effect=fake_run
    ):
        result = AccessRouter().extract("https://youtube.com/watch?v=1")

    assert result["content"] == "Hello\nWorld"
