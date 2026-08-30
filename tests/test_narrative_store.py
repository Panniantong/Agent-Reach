# -*- coding: utf-8 -*-
"""Evidence-ledger invariants for the narrative subsystem."""

import pytest

from agent_reach.narrative.ingest import ingest_text
from agent_reach.narrative.store import NarrativeStore


@pytest.fixture()
def store(tmp_path):
    return NarrativeStore(tmp_path / "narrative")


def _contract(store, *, resolution_date="2026-12-31"):
    return store.add_contract(
        scope_type="ticker",
        scope_id="NVDA",
        domain="information-technology",
        horizon="1y",
        statement="NVDA closes above the contract threshold by resolution.",
        resolution_date=resolution_date,
        criteria={"type": "price_above", "threshold": 200},
        resolution_source="quant_prices",
        source_ids=["serenity_aleabitoreddit"],
    )


def test_blob_hash_dedup_and_unverified_claim_isolation(store):
    first = ingest_text(
        store,
        text="因為資料中心需求持續成長，NVDA 2027 年營收可能上升，但目前只是來源主張。",
        title="Serenity note",
        ticker="NVDA",
        domain="information-technology",
    )
    second = ingest_text(
        store,
        text="因為資料中心需求持續成長，NVDA 2027 年營收可能上升，但目前只是來源主張。",
        title="duplicate",
        ticker="NVDA",
        domain="information-technology",
    )

    assert first["created"] is True
    assert second["created"] is False
    assert first["document"]["id"] == second["document"]["id"]
    assert len(list(store.blob_dir.iterdir())) == 1
    assert first["claims"]
    assert {claim["verification_state"] for claim in first["claims"]} == {"pending"}
    assert store.list_claims(state="verified") == []


def test_source_identities_and_conflict_flags_are_not_merged(store):
    sources = {row["id"]: row for row in store.list_sources()}

    assert "serenity_aleabitoreddit" in sources
    assert "huang_jingzhe" in sources
    assert (
        sources["serenity_aleabitoreddit"]["display_name"]
        != sources["huang_jingzhe"]["display_name"]
    )
    assert "affiliate_exchange" in sources["bonnie_blockchain"]["conflict_flags"]
    assert "affiliate_exchange" in sources["youtubercrypto"]["conflict_flags"]


def test_verified_claim_requires_qualified_evidence_and_frame_cap(store):
    imported = ingest_text(
        store,
        text="NVDA 的 2026 年價格上升可能由資料中心需求帶動。",
        ticker="NVDA",
        domain="information-technology",
    )
    claim_id = imported["claims"][0]["id"]

    with pytest.raises(ValueError, match="verified claims need"):
        store.review_claim(
            claim_id,
            verification_state="verified",
            tag="KNOWN",
            confidence="HIGH",
            reviewer="tester",
            reason="unsupported",
            evidence=[],
        )

    reviewed = store.review_claim(
        claim_id,
        verification_state="verified",
        tag="COMPUTED",
        confidence="HIGH",
        reviewer="tester",
        reason="Quant price artifact matched",
        evidence=[{"kind": "quant", "verified": True, "artifact": "NVDA.csv"}],
    )
    assert reviewed["verification_state"] == "verified"

    with pytest.raises(ValueError, match="cannot exceed LOW"):
        store.review_claim(
            claim_id,
            verification_state="reviewed_hypothesis",
            tag="FRAME",
            confidence="HIGH",
            reviewer="tester",
            reason="invalid confidence",
        )


def test_overlapping_contract_probabilities_do_not_need_to_sum_to_one(store):
    first = _contract(store)
    second = store.add_contract(
        scope_type="ticker",
        scope_id="NVDA",
        domain="information-technology",
        horizon="1y",
        statement="NVDA data-center revenue grows above the contract threshold.",
        resolution_date="2026-12-31",
        criteria={"type": "return_gte", "threshold": 0.1, "start_date": "2026-01-02"},
        resolution_source="quant_prices",
    )
    probabilities = []
    for contract, probability in ((first, 0.8), (second, 0.7)):
        row = store.add_forecast(
            contract_id=contract["id"],
            as_of="2026-01-01",
            probability_status="calibrated",
            probability=probability,
            lower_bound=probability - 0.1,
            upper_bound=probability + 0.1,
            model_name="fixture",
            model_version="v1",
            training_cutoff="2025-12-31",
        )
        probabilities.append(row["probability"])

    assert sum(probabilities) == pytest.approx(1.5)


def test_resolutions_are_append_only_and_human_override_is_effective(store):
    contract = _contract(store)
    automatic = store.add_resolution(
        contract_id=contract["id"],
        outcome=0,
        reason="automatic price rule",
        actor="test-auto",
    )
    human = store.add_resolution(
        contract_id=contract["id"],
        outcome=1,
        reason="official split adjustment",
        actor="tester",
        kind="human_override",
    )

    rows = store.list_resolutions(contract["id"])
    assert [row["id"] for row in rows] == [automatic["id"], human["id"]]
    assert store.effective_outcomes()[contract["id"]] == 1


def test_source_score_excludes_forecasts_after_contract_resolution(store):
    contract = _contract(store, resolution_date="2026-06-30")
    store.add_forecast(
        contract_id=contract["id"],
        as_of="2026-07-01",
        probability_status="calibrated",
        probability=0.9,
        lower_bound=0.8,
        upper_bound=0.95,
        model_name="future",
        model_version="v1",
        training_cutoff="2026-07-01",
    )
    store.add_resolution(
        contract_id=contract["id"],
        outcome=1,
        reason="resolved",
        actor="tester",
    )

    assert store.source_scores(domain="information-technology", horizon="1y") == []


def test_schema_v1_migrates_through_v3_with_resolution_source(tmp_path):
    root = tmp_path / "migration"
    first = NarrativeStore(root)
    with first._connect() as conn:
        conn.execute("ALTER TABLE event_contracts DROP COLUMN resolution_source")
        conn.execute("PRAGMA user_version=1")

    migrated = NarrativeStore(root)
    with migrated._connect() as conn:
        columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(event_contracts)").fetchall()
        }

    assert migrated.status()["schema_version"] == 3
    assert "resolution_source" in columns
    assert (root / "narrative.sqlite3.pre-v3.bak").is_file()
