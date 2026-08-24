# -*- coding: utf-8 -*-
"""Manual-ingest, source identity, and SSRF boundary tests."""

from pathlib import Path

import pytest

from agent_reach.narrative.ingest import (
    infer_source_id,
    ingest_file,
    ingest_text,
    validate_public_url,
)
from agent_reach.narrative.store import NarrativeStore


def _public_resolver(_host, _port):
    return [(2, 1, 6, "", ("93.184.216.34", 0))]


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/private",
        "http://10.0.0.2/data",
        "http://169.254.169.254/latest/meta-data",
        "file:///etc/passwd",
        "https://user:password@example.com/",
    ],
)
def test_url_safety_rejects_private_and_credential_targets(url):
    with pytest.raises(ValueError):
        validate_public_url(url, resolver=_public_resolver)


def test_url_safety_accepts_only_resolved_public_http_targets():
    assert (
        validate_public_url("https://example.com/research", resolver=_public_resolver)
        == "https://example.com/research"
    )


def test_report_seed_is_quarantined_and_claims_remain_pending(tmp_path):
    store = NarrativeStore(tmp_path / "ledger")
    report = tmp_path / "musk.md"
    report.write_text(
        "因為治理風險上升，2027 年公司估值可能下降；具體日期仍待查證。",
        encoding="utf-8",
    )

    result = ingest_file(store, report, domain="governance")

    assert result["document"]["metadata"]["quarantine"] is True
    assert result["document"]["verification_state"] == "pending"
    assert all(claim["verification_state"] == "pending" for claim in result["claims"])
    assert all(claim["tag"] == "GUESS" for claim in result["claims"])


def test_source_inference_keeps_named_identities_distinct(tmp_path):
    store = NarrativeStore(tmp_path / "ledger")

    serenity = ingest_text(
        store,
        text="Serenity 認為 2027 年半導體需求可能上升，這仍需 Quant 數據支持。",
        title="Serenity",
    )
    huang = ingest_text(
        store,
        text="黃靖哲認為 2027 年半導體需求可能下降，這仍需 Quant 數據支持。",
        title="黃靖哲",
    )
    bonnie = ingest_text(
        store,
        text="邦妮區塊鏈認為 2027 年加密採用可能增加，這仍需鏈上數據支持。",
        title="邦妮區塊鏈",
    )

    assert serenity["document"]["source_id"] == "serenity_aleabitoreddit"
    assert huang["document"]["source_id"] == "huang_jingzhe"
    assert bonnie["document"]["source_id"] == "bonnie_blockchain"
    assert "affiliate_exchange" in bonnie["claims"][0]["conflict_flags"]
    assert infer_source_id("科幣託 youtubercrypto") == "youtubercrypto"


def test_unsupported_file_type_is_rejected(tmp_path):
    store = NarrativeStore(tmp_path / "ledger")
    binary = Path(tmp_path / "payload.exe")
    binary.write_bytes(b"not executable content")

    with pytest.raises(ValueError, match="unsupported file type"):
        ingest_file(store, binary)
