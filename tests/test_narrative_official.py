# -*- coding: utf-8 -*-
"""Official SEC and policy source contracts."""

import json

from agent_reach.narrative.official import OfficialSourceAdapter
from agent_reach.narrative.quant import QuantAdapter
from agent_reach.narrative.research import ResearchService
from agent_reach.narrative.store import NarrativeStore


class _Response:
    def __init__(self, payload=None, content=b"", content_type="application/json"):
        self._payload = payload
        self.content = content or (
            json.dumps(payload).encode("utf-8") if payload is not None else b""
        )
        self.headers = {"content-type": content_type}

    def json(self):
        return self._payload

    def raise_for_status(self):
        return None


class _Session:
    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        for marker, response in self.routes:
            if marker in url:
                return response
        raise AssertionError(f"unexpected URL: {url}")


def test_sec_sync_preserves_pit_filing_and_amendment_without_claims(tmp_path):
    recent = {
        "accessionNumber": ["0001234567-26-000001", "0001234567-26-000002", "0001234567-26-000003"],
        "form": ["10-K", "10-K/A", "10-Q"],
        "filingDate": ["2026-08-20", "2026-08-25", "2026-09-02"],
        "acceptanceDateTime": ["20260820120000", "20260825130000", "20260902140000"],
        "reportDate": ["2026-06-30", "2026-06-30", "2026-08-31"],
        "primaryDocument": ["annual.htm", "annual-amend.htm", "future.htm"],
    }
    session = _Session([
        ("submissions/CIK0001234567.json", _Response({"filings": {"recent": recent}})),
        ("annual.htm", _Response(content=b"<html>annual filing</html>", content_type="text/html")),
        ("annual-amend.htm", _Response(content=b"<html>amended filing</html>", content_type="text/html")),
    ])
    store = NarrativeStore(tmp_path / "narrative")
    adapter = OfficialSourceAdapter(store=store, session=session)

    result = adapter.sync_sec_filings(
        "LITE",
        cik="1234567",
        as_of="2026-08-30",
        user_agent="Agent Reach research analyst@example.com",
    )

    assert len(result["filings"]) == 2
    assert result["claims_created"] == 0
    assert store.list_claims() == []
    documents = store.list_documents()
    assert {row["metadata"]["form"] for row in documents} == {"10-K", "10-K/A"}
    amended = next(row for row in documents if row["metadata"]["form"] == "10-K/A")
    assert amended["metadata"]["amendment"] is True
    assert all(row["as_of"] <= "2026-08-30" for row in documents)
    assert not any("future.htm" in url for url, _ in session.calls)
    assert store.list_source_coverage(run_id=result["run"]["id"])[0]["retrieved"] == 2

    research = ResearchService(store=store, quant=QuantAdapter(tmp_path / "quant"))
    pack = research.run_research("cpo-external-laser", as_of="2026-08-30")
    lite = next(row for row in pack["payload"]["companies"] if row["ticker"] == "LITE")
    assert len(lite["official_filings"]) == 2
    assert pack["payload"]["coverage"]["official_filings"] == 2
    assert pack["payload"]["evidence_grade"] == "E"


def test_federal_register_keeps_proposed_final_effective_states_separate(tmp_path):
    payload = {
        "count": 4,
        "results": [
            {
                "document_number": "2026-10001",
                "title": "Proposed export rule",
                "type": "Proposed Rule",
                "publication_date": "2026-08-01",
                "effective_on": "",
                "html_url": "https://www.federalregister.gov/d/2026-10001",
            },
            {
                "document_number": "2026-10002",
                "title": "Final export rule",
                "type": "Rule",
                "publication_date": "2026-08-02",
                "effective_on": "2026-10-01",
                "html_url": "https://www.federalregister.gov/d/2026-10002",
            },
            {
                "document_number": "2026-10003",
                "title": "Effective export rule",
                "type": "Rule",
                "publication_date": "2026-08-03",
                "effective_on": "2026-08-20",
                "html_url": "https://www.federalregister.gov/d/2026-10003",
            },
            {
                "document_number": "2026-10004",
                "title": "Future publication",
                "type": "Rule",
                "publication_date": "2026-09-03",
                "effective_on": "2026-09-20",
                "html_url": "https://www.federalregister.gov/d/2026-10004",
            },
        ],
    }
    store = NarrativeStore(tmp_path / "narrative")
    adapter = OfficialSourceAdapter(
        store=store,
        session=_Session([("documents.json", _Response(payload))]),
    )

    result = adapter.sync_federal_register(
        "export controls", as_of="2026-08-30", limit=20
    )

    assert {row["policy_state"] for row in result["documents"]} == {
        "proposed", "final", "effective"
    }
    assert result["claims_created"] == 0
    assert store.list_claims() == []
    assert all(
        row["metadata"]["company_impact_claimed"] is False
        for row in store.list_documents()
    )


def test_congress_bill_rejects_payload_updated_after_as_of(tmp_path):
    store = NarrativeStore(tmp_path / "narrative")
    session = _Session([(
        "/bill/119/hr/1234",
        _Response({"bill": {
            "title": "Fixture Act", "introducedDate": "2026-07-01",
            "updateDate": "2026-09-01T12:00:00Z",
            "latestAction": {"actionDate": "2026-09-01", "text": "Passed House"},
            "url": "https://api.congress.gov/v3/bill/119/hr/1234",
        }}),
    )])
    adapter = OfficialSourceAdapter(store=store, session=session)

    result = adapter.sync_congress_bill(
        congress=119, bill_type="hr", bill_number=1234,
        api_key="fixture-key", as_of="2026-08-30",
    )

    assert result["pit_eligible"] is False
    assert result["documents"] == []
    assert store.list_documents() == []
    coverage = store.list_source_coverage(run_id=result["run"]["id"])[0]
    assert coverage["index_only"] == 1


def test_regulations_excludes_records_modified_after_cutoff(tmp_path):
    payload = {
        "data": [
            {
                "id": "DOC-1",
                "type": "documents",
                "attributes": {
                    "title": "PIT docket document", "docketId": "DCK-1",
                    "documentType": "Notice", "postedDate": "2026-08-01",
                    "lastModifiedDate": "2026-08-20", "withdrawn": False,
                },
            },
            {
                "id": "DOC-2",
                "type": "documents",
                "attributes": {
                    "title": "Later modified document", "docketId": "DCK-1",
                    "documentType": "Rule", "postedDate": "2026-08-02",
                    "lastModifiedDate": "2026-09-02", "withdrawn": True,
                },
            },
        ]
    }
    store = NarrativeStore(tmp_path / "narrative")
    adapter = OfficialSourceAdapter(
        store=store,
        session=_Session([("/v4/documents", _Response(payload))]),
    )

    result = adapter.sync_regulations(
        "semiconductor", api_key="fixture-key", as_of="2026-08-30"
    )

    assert len(result["documents"]) == 1
    assert result["pit_excluded"] == 1
    assert store.list_documents()[0]["metadata"]["document_id"] == "DOC-1"
    assert result["claims_created"] == 0
