"""`xiaohongshu read` must map OpenCLI's {field, value} rows into one note item."""

import pytest

from agent_reach.channels.xiaohongshu import XiaoHongShuChannel
from agent_reach.runtime.dispatch import run_action

NOTE = "https://www.xiaohongshu.com/explore/abc123?xsec_token=test"

ROWS = [
    {"field": "title", "value": "A title"},
    {"field": "author", "value": "An author"},
    {"field": "content", "value": "The body"},
    {"field": "likes", "value": "7"},
]


def _read(monkeypatch, output):
    from agent_reach.channels import xiaohongshu

    calls = []

    def command(site, args, **kwargs):
        calls.append(args)
        return output

    monkeypatch.setattr(xiaohongshu, "opencli_call", command)
    result = run_action(XiaoHongShuChannel(), "read", {"target": NOTE}, only_backend="opencli")
    assert calls == [["note", NOTE]]
    return result


@pytest.mark.parametrize("output", [ROWS, {"ok": True, "data": ROWS}],
                         ids=["bare list", "OpenCLI 2.0 {ok, data} envelope"])
def test_read_maps_field_value_rows_into_one_note(monkeypatch, output):
    result = _read(monkeypatch, output)

    assert result["ok"]
    assert len(result["items"]) == 1
    item = result["items"][0]
    assert item["title"] == "A title"
    assert item["author"] == "An author"
    assert item["text"] == "The body"
    assert item["url"] == NOTE


def test_read_reports_a_missing_note_for_an_empty_envelope(monkeypatch):
    result = _read(monkeypatch, {"ok": True, "data": []})

    assert not result["ok"]
    assert result["error"]["code"] == "NOT_FOUND"
