# -*- coding: utf-8 -*-
"""Tests for evidence ledger JSONL helpers."""

import json

import pytest

from agent_reach.ledger import (
    append_ledger_record,
    build_ledger_record,
    default_run_id,
    ledger_input_paths,
    merge_ledger_inputs,
    query_ledger_input,
    save_collection_result,
    save_collection_result_sharded,
    shard_ledger_path,
    summarize_ledger_input,
    validate_ledger_input,
)
from agent_reach.results import build_error, build_item, build_result


def _success_result():
    item = build_item(
        item_id="item-1",
        kind="page",
        title="Example",
        url="https://example.com",
        text="hello",
        author="alice",
        published_at="2026-04-10T00:00:00Z",
        source="web",
    )
    return build_result(
        ok=True,
        channel="web",
        operation="read",
        items=[item],
        raw={"ok": True},
        meta={"input": "https://example.com"},
        error=None,
    )


def _error_result():
    return build_result(
        ok=False,
        channel="github",
        operation="read",
        raw=None,
        meta={"input": "missing"},
        error=build_error(
            code="unknown_channel",
            message="Unknown channel",
            details={},
        ),
    )


def test_build_ledger_record_success_shape():
    payload = _success_result()
    record = build_ledger_record(payload, run_id="run-1", input_value="example.com")

    assert record["schema_version"]
    assert record["record_type"] == "collection_result"
    assert record["run_id"] == "run-1"
    assert record["channel"] == "web"
    assert record["operation"] == "read"
    assert record["input"] == "example.com"
    assert record["ok"] is True
    assert record["count"] == 1
    assert record["item_ids"] == ["item-1"]
    assert record["urls"] == ["https://example.com"]
    assert record["error_code"] is None
    assert record["result"] == payload


def test_build_ledger_record_preserves_relevance_metadata():
    payload = _success_result()
    record = build_ledger_record(
        payload,
        run_id="run-1",
        intent="official_docs",
        query_id="q01",
        source_role="web_discovery",
    )

    assert record["intent"] == "official_docs"
    assert record["query_id"] == "q01"
    assert record["source_role"] == "web_discovery"


def test_build_ledger_record_error_shape():
    payload = _error_result()
    record = build_ledger_record(payload, run_id="run-2")

    assert record["run_id"] == "run-2"
    assert record["input"] == "missing"
    assert record["ok"] is False
    assert record["count"] == 0
    assert record["item_ids"] == []
    assert record["urls"] == []
    assert record["error_code"] == "unknown_channel"
    assert record["result"] == payload


def test_append_ledger_record_writes_jsonl(tmp_path):
    path = tmp_path / ".agent-reach" / "evidence.jsonl"
    first = build_ledger_record(_success_result(), run_id="run-1")
    second = build_ledger_record(_error_result(), run_id="run-1")

    append_ledger_record(path, first)
    append_ledger_record(path, second)

    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["ok"] is True
    assert json.loads(lines[1])["error_code"] == "unknown_channel"


def test_append_ledger_record_escapes_unicode_line_separators(tmp_path):
    path = tmp_path / "evidence.jsonl"
    payload = _success_result()
    payload["items"][0]["text"] = "alpha\u2028beta\u2029gamma\u0085delta"
    record = build_ledger_record(payload, run_id="run-1")

    append_ledger_record(path, record)

    text = path.read_text(encoding="utf-8")
    assert "\u2028" not in text
    assert "\u2029" not in text
    assert "\u0085" not in text
    assert "\\u2028" in text
    assert "\\u2029" in text
    assert "\\u0085" in text
    assert path.read_bytes().count(b"\n") == 1
    assert json.loads(text)["result"]["items"][0]["text"] == "alpha\u2028beta\u2029gamma\u0085delta"


def test_save_collection_result_surfaces_invalid_path(tmp_path):
    directory_path = tmp_path / "already-a-directory"
    directory_path.mkdir()

    with pytest.raises(OSError):
        save_collection_result(directory_path, _success_result(), run_id="run-1")


def test_default_run_id_prefers_environment(monkeypatch):
    monkeypatch.setenv("AGENT_REACH_RUN_ID", "configured-run")

    assert default_run_id() == "configured-run"


def test_default_run_id_falls_back_to_timestamp(monkeypatch):
    monkeypatch.delenv("AGENT_REACH_RUN_ID", raising=False)

    assert default_run_id().startswith("run-")


def test_shard_ledger_path_uses_requested_strategy(tmp_path):
    assert shard_ledger_path(tmp_path, channel="web", operation="read", shard_by="channel").name == "web.jsonl"
    assert shard_ledger_path(tmp_path, channel="web", operation="read", shard_by="operation").name == "read.jsonl"
    assert shard_ledger_path(tmp_path, channel="web", operation="read", shard_by="channel-operation").name == "web__read.jsonl"


def test_save_collection_result_sharded_writes_expected_file(tmp_path):
    record, shard_path = save_collection_result_sharded(
        tmp_path / "ledger",
        _success_result(),
        run_id="run-3",
        shard_by="channel-operation",
    )

    assert record["run_id"] == "run-3"
    assert shard_path.name == "web__read.jsonl"
    assert shard_path.exists()


def test_ledger_input_paths_reads_directory(tmp_path):
    source_dir = tmp_path / "ledger"
    source_dir.mkdir()
    (source_dir / "web.jsonl").write_text("{}", encoding="utf-8")
    (source_dir / "rss.jsonl").write_text("{}", encoding="utf-8")

    paths = ledger_input_paths(source_dir)

    assert [path.name for path in paths] == ["rss.jsonl", "web.jsonl"]


def test_merge_ledger_inputs_combines_shards(tmp_path):
    source_dir = tmp_path / "ledger"
    source_dir.mkdir()
    (source_dir / "web.jsonl").write_text('{"record_type":"collection_result","id":"1"}\n', encoding="utf-8")
    (source_dir / "rss.jsonl").write_text('{"record_type":"collection_result","id":"2"}\n', encoding="utf-8")

    payload = merge_ledger_inputs(source_dir, tmp_path / "merged.jsonl")

    assert payload["files_merged"] == 2
    assert payload["records_written"] == 2
    assert payload["inputs"][0].endswith("rss.jsonl")


def test_merge_ledger_inputs_preserves_unicode_line_separator_records(tmp_path):
    source_dir = tmp_path / "ledger"
    source_dir.mkdir()
    record = build_ledger_record(_success_result(), run_id="run-1")
    record["result"]["items"][0]["text"] = "alpha\u2028beta"
    (source_dir / "web.jsonl").write_text(
        json.dumps(record, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    output_path = tmp_path / "merged.jsonl"

    payload = merge_ledger_inputs(source_dir, output_path)

    assert payload["records_written"] == 1
    assert output_path.read_bytes().count(b"\n") == 1
    output_text = output_path.read_text(encoding="utf-8")
    assert "\\u2028" in output_text
    assert json.loads(output_text)["result"]["items"][0]["text"] == "alpha\u2028beta"


def test_validate_ledger_input_handles_unicode_line_separator_records(tmp_path):
    path = tmp_path / "evidence.jsonl"
    record = build_ledger_record(_success_result(), run_id="run-1")
    record["result"]["items"][0]["text"] = "alpha\u2028beta"
    path.write_text(json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8")

    payload = validate_ledger_input(path)

    assert payload["valid"] is True
    assert payload["records"] == 1
    assert payload["collection_results"] == 1
    assert payload["items_seen"] == 1
    assert payload["invalid_lines"] == 0


def test_validate_ledger_input_reports_diagnostics(tmp_path):
    path = tmp_path / "evidence.jsonl"
    missing_metadata = build_ledger_record(_success_result(), run_id="run-1")
    oversized_raw_error = build_ledger_record(
        _error_result(),
        run_id="run-1",
        intent="external_smoke",
        query_id="github-missing",
        source_role="repo_anchor",
    )
    oversized_raw_error["result"]["raw"] = "x" * 100_001
    path.write_text(
        "".join(
            json.dumps(record, ensure_ascii=False) + "\n"
            for record in (missing_metadata, oversized_raw_error)
        ),
        encoding="utf-8",
    )

    payload = validate_ledger_input(path)

    assert payload["valid"] is True
    assert payload["counts_scope"] == "parseable_records_only"
    assert payload["ok_records"] == 1
    assert payload["error_records"] == 1
    assert payload["channel_counts"] == {"web": 1, "github": 1}
    assert payload["operation_counts"] == {"read": 2}
    assert payload["error_codes"] == {"unknown_channel": 1}
    assert payload["missing_metadata"]["intent"] == 1
    assert payload["missing_metadata"]["query_id"] == 1
    assert payload["missing_metadata"]["source_role"] == 1
    assert payload["missing_metadata"]["samples"][0]["channel"] == "web"
    assert payload["large_raw_payload_threshold"] == 100_000
    assert payload["large_raw_payloads"][0]["channel"] == "github"
    assert payload["large_raw_payloads"][0]["raw_length"] == 100_001


def test_validate_ledger_input_can_require_metadata(tmp_path):
    path = tmp_path / "evidence.jsonl"
    record = build_ledger_record(_success_result(), run_id="run-1")
    path.write_text(json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8")

    payload = validate_ledger_input(path, require_metadata=True)

    assert payload["require_metadata"] is True
    assert payload["valid"] is False
    assert payload["missing_metadata"]["records"] == 1


def test_summarize_ledger_input_returns_health_counts(tmp_path):
    path = tmp_path / "evidence.jsonl"
    record = build_ledger_record(
        _success_result(),
        run_id="run-1",
        intent="official_docs",
        query_id="q01",
        source_role="web_discovery",
    )
    path.write_text(json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8")

    payload = summarize_ledger_input(path)

    assert payload["command"] == "ledger summarize"
    assert payload["records"] == 1
    assert payload["items_seen"] == 1
    assert payload["intent_counts"] == {"official_docs": 1}
    assert payload["query_id_counts"] == {"q01": 1}
    assert payload["source_role_counts"] == {"web_discovery": 1}


def test_query_ledger_input_filters_and_projects(tmp_path):
    path = tmp_path / "evidence.jsonl"
    records = [
        build_ledger_record(_success_result(), run_id="run-1"),
        build_ledger_record(_error_result(), run_id="run-1"),
    ]
    path.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )

    payload = query_ledger_input(
        path,
        filters=["channel == github", "ok == false"],
        fields=["channel", "ok", "source.file", "source.line"],
    )

    assert payload["command"] == "ledger query"
    assert payload["records_scanned"] == 2
    assert payload["matched_records"] == 1
    assert payload["returned_records"] == 1
    assert payload["matches"][0]["channel"] == "github"
    assert payload["matches"][0]["ok"] is False
    assert payload["matches"][0]["source.file"].endswith("evidence.jsonl")
    assert payload["matches"][0]["source.line"] == 2


def test_query_ledger_input_rejects_invalid_filter(tmp_path):
    path = tmp_path / "evidence.jsonl"
    path.write_text(json.dumps(build_ledger_record(_success_result(), run_id="run-1")) + "\n", encoding="utf-8")

    with pytest.raises(ValueError):
        query_ledger_input(path, filters=["channel github"])
