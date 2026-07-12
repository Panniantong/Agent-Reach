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
    with patch("agent_reach.access.AccessRouter.read", return_value={
        "platform": "twitter", "backend": "twitter-cli", "content": {"id": "1"}
    }):
        result = _run(["extract", "https://x.com/a/status/1", "--json"], capsys)
    assert result["status"] == "success"
    assert result["platform"] == "twitter"
    assert result["content"] == {"id": "1"}


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
    with patch("agent_reach.access.subprocess.run", return_value=completed) as run:
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
