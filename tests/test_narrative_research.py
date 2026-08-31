# -*- coding: utf-8 -*-
"""Industry research pack, typed graph, and PIT data-contract tests."""

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from agent_reach.narrative.quant import QuantAdapter
from agent_reach.narrative.research import ResearchService
from agent_reach.narrative.research import draft_thesis_unit
from agent_reach.narrative.serenity_source import load_x_subs_jsonl
from agent_reach.narrative.store import NarrativeStore


def _snapshot(root: Path):
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*") if path.is_file()
    }


@pytest.fixture()
def research_quant_root(tmp_path):
    root = tmp_path / "quant"
    tradingview = root / "tradingview" / "2026Q2PIT"
    tradingview.mkdir(parents=True)
    tickers = ["LITE", "COHR", "AAOI", "SIVE.ST"]
    for index, ticker in enumerate(tickers):
        (tradingview / f"{ticker}.csv").write_text(
            "time,close,Volume,Enterprise value to EBITDA ratio\n"
            f"2026-08-28,{50 + index},1000000,{8 + index}\n"
            f"2026-08-31,{60 + index},2000000,{9 + index}\n",
            encoding="utf-8",
        )

    snapshot_dir = root / "finviz" / "screener" / "v151" / "snapshots" / "2026-08-29"
    snapshot_dir.mkdir(parents=True)
    csv_path = snapshot_dir / "postclose.csv"
    rows = ["Ticker,Company,Asset Type,EV/EBITDA,EV/Sales,Price"]
    for index, ticker in enumerate(tickers):
        rows.append(f"{ticker},{ticker} Corp,,{10 + index},{4 + index},{100 + index}")
    rows.append("SPY,SPDR S&P 500,ETF,20,10,600")
    csv_path.write_text("\n".join(rows), encoding="utf-8")
    digest = hashlib.sha256(csv_path.read_bytes()).hexdigest()
    (snapshot_dir / "postclose.json").write_text(
        json.dumps(
            {
                "artifact_id": "fixture-v151",
                "artifact_contract_version": "finviz-research-artifact-v1",
                "as_of": "2026-08-29",
                "session_date": "2026-08-28",
                "fetched_at": "2026-08-29T21:00:00+00:00",
                "observed_slot": "postclose",
                "session_mismatch": False,
                "status": "ok",
                "paths": {"snapshot_csv": str(csv_path)},
                "metrics": {"normalized_csv_sha256": digest},
                "llm_involvement": "none",
                "orders_generated": False,
            }
        ),
        encoding="utf-8",
    )
    return root


def test_tradingview_and_finviz_adapters_are_pit_and_zero_write(research_quant_root):
    before = _snapshot(research_quant_root)
    adapter = QuantAdapter(research_quant_root)
    tv = adapter.read_tradingview_pit("LITE", as_of="2026-08-29")
    finviz = adapter.read_finviz_snapshot("LITE", as_of="2026-08-30")
    etf = adapter.read_finviz_snapshot("SPY", as_of="2026-08-30")
    after = _snapshot(research_quant_root)

    assert before == after
    assert tv["status"] == "ok"
    assert tv["as_of"].startswith("2026-08-28")
    assert tv["future_rows_excluded"] == 1
    assert finviz["status"] == "ok"
    assert finviz["session_date"] == "2026-08-28"
    assert etf["status"] == "excluded_non_company"


def test_missing_tradingview_file_never_follows_an_external_fallback(research_quant_root):
    result = QuantAdapter(research_quant_root).read_tradingview_pit("NVDA", as_of="2026-08-30")

    assert result["status"] == "missing"
    assert "no fallback followed" in " ".join(result["issues"])
    assert str(research_quant_root.resolve()) in result["path"]


def test_research_pack_is_deterministic_typed_and_recommend_only(tmp_path, research_quant_root):
    store = NarrativeStore(tmp_path / "narrative")
    service = ResearchService(store=store, quant=QuantAdapter(research_quant_root))
    before = _snapshot(research_quant_root)

    first = service.run_research("cpo-external-laser", as_of="2026-08-30")
    second = service.run_research("cpo-external-laser", as_of="2026-08-30")
    after = _snapshot(research_quant_root)

    assert before == after
    assert first["pack_created"] is True
    assert second["pack_created"] is False
    assert first["pack"]["content_hash"] == second["pack"]["content_hash"]
    assert first["payload"]["evidence_grade"] == "C"
    assert first["payload"]["orders_generated"] is False
    assert first["payload"]["bottleneck_contract"]["status"] == "candidate"
    assert all(edge["state"] == "proposed" for edge in first["payload"]["graph"]["edges"])
    assert all(edge["tag"] == "FRAME" for edge in first["payload"]["graph"]["edges"])
    assert all(
        len(company["valuation_snapshots"]) == 3
        for company in first["payload"]["companies"]
    )
    assert any(
        row["status"] == "computed_metric_range"
        for row in first["payload"]["companies"][0]["valuation_snapshots"]
    )


def test_bottleneck_observed_requires_two_strong_dimensions(tmp_path):
    store = NarrativeStore(tmp_path / "narrative")
    run = store.create_research_run(slice_id="fixture", universe_scope="fixture", as_of="2026-08-30")

    with pytest.raises(ValueError, match="two dimensions"):
        store.add_bottleneck_contract(
            run_id=run["id"],
            title="Fixture bottleneck",
            resolution_date="2027-08-30",
            status="observed",
            dimensions={"capacity": {"grade": "A"}},
        )

    row = store.add_bottleneck_contract(
        run_id=run["id"],
        title="Fixture bottleneck",
        resolution_date="2027-08-30",
        status="observed",
        dimensions={"capacity": {"grade": "A"}, "qualification": {"grade": "B"}},
    )
    assert row["status"] == "observed"


def test_stress_test_is_pack_bound_and_cannot_mutate_evidence(tmp_path, research_quant_root):
    service = ResearchService(
        store=NarrativeStore(tmp_path / "narrative"),
        quant=QuantAdapter(research_quant_root),
    )
    result = service.run_research("cpo-external-laser", as_of="2026-08-30")
    pack_id = result["pack"]["id"]

    critique = service.stress_test(pack_id, "What is the strongest reason the scarce layer is wrong?")

    assert critique["mutated"] is False
    assert critique["can_write_evidence"] is False
    assert critique["can_write_probability"] is False
    assert critique["llm_involvement"] == "none"


def test_relationship_contract_has_no_probability_before_calibration(tmp_path, research_quant_root):
    service = ResearchService(
        store=NarrativeStore(tmp_path / "narrative"),
        quant=QuantAdapter(research_quant_root),
    )
    contract = service.create_relationship_contract(
        {
            "ticker": "LITE",
            "statement": "LITE and a named customer disclose an ELS supply relationship.",
            "resolution_date": "2027-08-30",
            "criteria": {"named_counterparty": "fixture"},
        }
    )
    relationships = service.relationships(ticker="LITE")

    assert contract["criteria"]["kind"] == "official_named_relationship"
    assert relationships["contracts"][0]["id"] == contract["id"]
    assert relationships["relationships"] == []


def test_serenity_backfill_keeps_translation_out_of_evidence_and_learns_literal_patterns(
    tmp_path, research_quant_root
):
    now = datetime.now(timezone.utc)
    first_url = "https://x.com/aleabitoreddit/status/1001"
    posts = [
        SimpleNamespace(
            title="first",
            url=first_url,
            text="$LITE CPO capacity qualification risk is the bottleneck.",
            ts=(now - timedelta(days=1)).isoformat(),
            extra={"isRetweet": False},
        ),
        SimpleNamespace(
            title="duplicate",
            url=first_url,
            text="$LITE duplicate payload",
            ts=(now - timedelta(days=1)).isoformat(),
            extra={"isRetweet": False},
        ),
        SimpleNamespace(
            title="second",
            url="https://x.com/aleabitoreddit/status/1002",
            text="$COHR external light capacity and backlog matter.",
            ts=(now - timedelta(days=2)).isoformat(),
            extra={"isRetweet": False},
        ),
        SimpleNamespace(
            title="pure retweet",
            url="https://x.com/aleabitoreddit/status/1003",
            text="RT capacity",
            ts=(now - timedelta(days=3)).isoformat(),
            extra={"isRetweet": True},
        ),
    ]
    service = ResearchService(
        store=NarrativeStore(tmp_path / "narrative"),
        quant=QuantAdapter(research_quant_root),
    )

    result = service.serenity_backfill(
        days=90,
        count=2000,
        translations={first_url: {"zh_hant": "翻譯不可當證據", "en": "translated text"}},
        fetcher=lambda handle, count, config: posts,
    )

    assert result["retrieved"] == 2
    assert result["deduplicated"] == 1
    assert result["coverage_complete"] is False
    assert service.coverage(run_id=result["run"]["id"])["complete"] is False
    claims = service.store.list_claims(domain="serenity_method")
    assert len(claims) == 2
    assert all("翻譯不可當證據" not in claim["text"] for claim in claims)
    documents = service.store.list_documents()
    translated = next(row for row in documents if row["source_url"] == first_url)
    body = json.loads(Path(translated["blob_path"]).read_text(encoding="utf-8"))
    assert body["original"].startswith("$LITE")
    assert body["zh_hant"] == "翻譯不可當證據"
    assert body["thesis_unit"]["extraction_status"] == "literal_signals_pending_review"
    assert body["thesis_unit"]["themes"][0]["tag"] == "FRAME"
    units = service.serenity_units(limit=10)
    assert len(units) == 2
    assert next(row for row in units if row["source_url"] == first_url)["en"] == "translated text"
    dimensions = result["method_profile"]["profile"]["dimensions"]
    assert dimensions["capacity_lead_time"]["observed_count"] == 2
    assert dimensions["capacity_lead_time"]["repeated_in_independent_posts"] is True
    assert result["method_profile"]["voting_weight"] is None


def test_serenity_rate_limit_is_recorded_without_claiming_zero_posts(
    tmp_path, research_quant_root
):
    service = ResearchService(
        store=NarrativeStore(tmp_path / "narrative"),
        quant=QuantAdapter(research_quant_root),
    )

    def rate_limited(handle, count, config):
        raise RuntimeError("rate limited by upstream")

    result = service.serenity_backfill(days=1, fetcher=rate_limited)
    coverage = service.coverage(run_id=result["run"]["id"])

    assert result["retrieved"] == 0
    assert result["coverage_complete"] is False
    assert coverage["totals"]["rate_limited"] == 1
    assert coverage["zero_means_unknown"] is True


def test_x_subs_jsonl_is_read_only_bilingual_evidence_input(
    tmp_path, research_quant_root
):
    now = datetime.now(timezone.utc)
    archive_path = tmp_path / "posts.jsonl"
    records = [
        {
            "id": "10001",
            "timestamp": (now - timedelta(days=1)).isoformat(),
            "images": ["https://pbs.twimg.com/media/fixture"],
            "en": "$LITE demand capacity qualification risk.",
            "zh": "LITE 需求、產能、認證與風險。",
        },
        {
            "id": "10001",
            "timestamp": (now - timedelta(days=1)).isoformat(),
            "images": [],
            "en": "$LITE demand capacity qualification risk.",
            "zh": "LITE 需求、產能、認證與風險。",
        },
        {
            "id": "10002",
            "timestamp": (now - timedelta(days=2)).isoformat(),
            "images": [],
            "en": "$COHR backlog and lead time matter.",
            "zh": "COHR 積壓訂單與交期很重要。",
        },
    ]
    archive_path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in records)
        + "\nnot-json\n",
        encoding="utf-8",
    )

    archive = load_x_subs_jsonl(archive_path)
    assert len(archive.items) == 3
    assert archive.manifest["malformed_records"] == 1
    assert archive.manifest["read_only"] is True
    assert archive.items[0].extra["subscriberOnly"] is True
    assert archive.items[0].extra["originalTextVerified"] is True

    service = ResearchService(
        store=NarrativeStore(tmp_path / "narrative"),
        quant=QuantAdapter(research_quant_root),
    )
    result = service.serenity_backfill(
        days=90,
        count=20,
        source_jsonl=archive_path,
        fetcher=lambda handle, count, config: [],
    )

    assert result["retrieved"] == 2
    assert result["deduplicated"] == 1
    assert result["source_manifest"]["backend"] == "x_subs_downloader_jsonl"
    units = service.serenity_units(limit=10)
    lite = next(row for row in units if row["source_url"].endswith("/10001"))
    assert lite["original"].startswith("$LITE")
    assert lite["zh_hant"].startswith("LITE")
    claims = service.store.list_claims(domain="serenity_method")
    assert all("積壓訂單" not in claim["text"] for claim in claims)


def test_serenity_methodology_requires_repeated_joint_source_evidence(
    tmp_path, research_quant_root
):
    now = datetime.now(timezone.utc)
    posts = [
        SimpleNamespace(
            title="method one",
            url="https://x.com/aleabitoreddit/status/20001",
            text=(
                "$LITE demand policy capacity qualification pricing revenue "
                "catalyst risk."
            ),
            ts=(now - timedelta(days=1)).isoformat(),
            extra={"isRetweet": False},
        ),
        SimpleNamespace(
            title="method two",
            url="https://x.com/aleabitoreddit/status/20002",
            text=(
                "$COHR shipment export control lead time qualified price increase "
                "margin ramp failure."
            ),
            ts=(now - timedelta(days=2)).isoformat(),
            extra={"isRetweet": False},
        ),
    ]
    service = ResearchService(
        store=NarrativeStore(tmp_path / "narrative"),
        quant=QuantAdapter(research_quant_root),
    )
    service.serenity_backfill(
        days=90,
        count=20,
        fetcher=lambda handle, count, config: posts,
    )

    methodology = service.serenity_methodology(persist=False)

    assert methodology["corpus"]["independent_documents"] == 2
    assert methodology["sequence_status"] == "not_established_by_literal_cooccurrence"
    assert methodology["voting_weight"] is None
    candidates = {
        row["id"]: row
        for row in methodology["candidate_logic"]
        if row["repeated_in_independent_posts"]
    }
    assert set(candidates) == {
        "forcing_function",
        "constraint_test",
        "value_capture_test",
        "resolution_test",
    }
    assert all(row["tag"] == "INFERRED" for row in candidates.values())
    assert all(row["confidence"] == "LOW" for row in candidates.values())
    assert methodology["dimensions"]["capacity_lead_time"]["evidence_posts"]
    assert methodology["corpus"]["ticker_counts"] == {"COHR": 1, "LITE": 1}


def test_method_signal_english_terms_use_token_boundaries():
    unit = draft_thesis_unit(
        "The impact is material, but this post contains no enacted policy.",
        "2026-08-31T00:00:00+00:00",
    )

    assert "act" not in unit["method_signals"].get("policy_exposure", [])


def test_typed_edge_cannot_skip_review_or_verify_unreviewed_evidence(tmp_path):
    store = NarrativeStore(tmp_path / "narrative")
    run = store.create_research_run(slice_id="fixture", universe_scope="fixture", as_of="2026-08-30")
    graph = store.create_graph(run_id=run["id"], slice_id="fixture", as_of="2026-08-30")
    source = store.add_graph_node(
        graph_id=graph["id"], node_type="Company", label="Supplier"
    )
    target = store.add_graph_node(
        graph_id=graph["id"], node_type="Company", label="Customer"
    )
    edge = store.add_graph_edge(
        graph_id=graph["id"],
        source_node_id=source["id"],
        target_node_id=target["id"],
        edge_type="commercial_relationship",
    )

    with pytest.raises(ValueError, match="invalid edge transition"):
        store.review_graph_edge(
            edge["id"], state="verified", tag="KNOWN", confidence="HIGH",
            reviewer="tester", reason="skip", evidence=[],
        )

    supported = store.review_graph_edge(
        edge["id"],
        state="supported",
        tag="INFERRED",
        confidence="LOW",
        reviewer="tester",
        reason="single secondary clue",
        evidence=[{"stance": "support", "grade": "C", "source_id": "serenity_aleabitoreddit"}],
    )
    assert supported["state"] == "supported"

    with pytest.raises(ValueError, match="strong reviewed support"):
        store.review_graph_edge(
            edge["id"], state="verified", tag="KNOWN", confidence="HIGH",
            reviewer="tester", reason="still no official claim", evidence=[],
        )

    document, _ = store.add_document(
        content=b"official relationship disclosure",
        source_id="sec_edgar",
        source_url="https://www.sec.gov/Archives/fixture",
    )
    claim = store.add_claim(
        document_id=document["id"],
        text="Supplier named Customer in an official filing.",
        source_id="sec_edgar",
        source_url="https://www.sec.gov/Archives/fixture",
    )
    reviewed = store.review_claim(
        claim["id"],
        verification_state="verified",
        tag="KNOWN",
        confidence="HIGH",
        reviewer="tester",
        reason="direct official filing",
        evidence=[{"kind": "official", "verified": True, "accession": "fixture"}],
    )
    verified = store.review_graph_edge(
        edge["id"],
        state="verified",
        tag="KNOWN",
        confidence="HIGH",
        reviewer="tester",
        reason="direct named disclosure",
        evidence=[{
            "stance": "support", "grade": "A", "claim_id": reviewed["id"],
            "source_id": "sec_edgar", "source_url": "https://www.sec.gov/Archives/fixture",
        }],
    )
    assert verified["state"] == "verified"
    assert verified["metadata"]["reviews"][-1]["to"] == "verified"


def test_bottleneck_transition_requires_sequence_and_two_strong_dimensions(tmp_path):
    store = NarrativeStore(tmp_path / "narrative")
    run = store.create_research_run(slice_id="fixture", universe_scope="fixture", as_of="2026-08-30")
    bottleneck = store.add_bottleneck_contract(
        run_id=run["id"],
        title="Qualified capacity",
        resolution_date="2027-08-30",
        easing_threshold={"supply_load_ratio": 1.2},
    )

    with pytest.raises(ValueError, match="invalid bottleneck transition"):
        store.transition_bottleneck(
            bottleneck["id"], status="resolved", reviewer="tester", reason="skip"
        )
    with pytest.raises(ValueError, match="two dimensions"):
        store.transition_bottleneck(
            bottleneck["id"],
            status="observed",
            reviewer="tester",
            reason="one metric",
            dimensions={"capacity": {"grade": "A"}},
        )

    observed = store.transition_bottleneck(
        bottleneck["id"],
        status="observed",
        reviewer="tester",
        reason="capacity and qualification",
        dimensions={"capacity": {"grade": "A"}, "qualification": {"grade": "B"}},
    )
    easing = store.transition_bottleneck(
        bottleneck["id"], status="easing", reviewer="tester", reason="threshold approached"
    )
    resolved = store.transition_bottleneck(
        bottleneck["id"], status="resolved", reviewer="tester", reason="threshold crossed"
    )

    assert observed["status"] == "observed"
    assert easing["status"] == "easing"
    assert resolved["status"] == "resolved"
    assert resolved["resolved_at"]
