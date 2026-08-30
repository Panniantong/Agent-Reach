# -*- coding: utf-8 -*-
"""User-triggered official-document adapters for SEC and policy evidence.

Adapters only call public upstream HTTP APIs, preserve immutable response content,
and never convert a filing or rule into a company-impact claim automatically.
"""

from __future__ import annotations

import json
import posixpath
import re
from datetime import date
from typing import Any, Optional
from urllib.parse import quote

import requests

from agent_reach.config import Config
from agent_reach.narrative.store import NarrativeStore

SEC_DATA = "https://data.sec.gov"
SEC_WWW = "https://www.sec.gov"
FEDERAL_REGISTER_API = "https://www.federalregister.gov/api/v1"
CONGRESS_API = "https://api.congress.gov/v3"
REGULATIONS_API = "https://api.regulations.gov/v4"
SEC_FORMS = (
    "10-K", "10-K/A", "10-Q", "10-Q/A", "8-K", "8-K/A",
    "20-F", "20-F/A", "6-K", "6-K/A",
)
MAX_OFFICIAL_BYTES = 25 * 1024 * 1024


def _cutoff(value: str) -> str:
    text = str(value or date.today().isoformat()).strip()[:10]
    date.fromisoformat(text)
    return text


def _date_prefix(value: str) -> str:
    text = str(value or "").strip()
    if re.match(r"^\d{8}", text):
        return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
    return text[:10]


def _policy_state(document_type: str, publication_date: str, effective_on: str, cutoff: str) -> str:
    kind = str(document_type or "").casefold()
    if "proposed" in kind:
        return "proposed"
    if effective_on and effective_on[:10] <= cutoff:
        return "effective"
    if "rule" in kind:
        return "final"
    return "notice"


class OfficialSourceAdapter:
    """Fetch official records into immutable narrative blobs after explicit action."""

    def __init__(
        self,
        store: Optional[NarrativeStore] = None,
        config: Optional[Config] = None,
        session: Optional[requests.Session] = None,
    ):
        self.config = config or Config()
        self.store = store or NarrativeStore(config=self.config)
        self.session = session or requests.Session()

    def _get(self, url: str, *, headers: Optional[dict] = None, params: Optional[dict] = None):
        response = self.session.get(url, headers=headers or {}, params=params or {}, timeout=45)
        response.raise_for_status()
        content = bytes(response.content or b"")
        if len(content) > MAX_OFFICIAL_BYTES:
            raise ValueError("official response exceeds 25 MiB limit")
        return response

    @staticmethod
    def _json(response) -> dict:
        try:
            payload = response.json()
        except Exception as exc:  # noqa: BLE001
            raise ValueError("official endpoint returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise ValueError("official endpoint JSON must be an object")
        return payload

    def _sec_user_agent(self, supplied: str) -> str:
        value = str(supplied or self.config.get("sec_user_agent", "") or "").strip()
        if len(value) < 8 or "@" not in value:
            raise ValueError("SEC sync requires a descriptive --user-agent containing contact email")
        return value

    def _resolve_cik(self, ticker: str, *, headers: dict) -> str:
        payload = self._json(
            self._get(f"{SEC_WWW}/files/company_tickers.json", headers=headers)
        )
        symbol = ticker.upper().strip()
        for row in payload.values():
            if isinstance(row, dict) and str(row.get("ticker") or "").upper() == symbol:
                return str(row.get("cik_str") or "").zfill(10)
        raise LookupError(f"SEC CIK not found for ticker: {symbol}")

    def sync_sec_filings(
        self,
        ticker: str,
        *,
        cik: str = "",
        as_of: str = "",
        limit: int = 40,
        user_agent: str = "",
        forms: tuple[str, ...] = SEC_FORMS,
    ) -> dict:
        symbol = ticker.upper().strip()
        if not symbol or not re.fullmatch(r"[A-Z0-9.-]{1,12}", symbol):
            raise ValueError("invalid ticker")
        cutoff = _cutoff(as_of)
        headers = {"User-Agent": self._sec_user_agent(user_agent), "Accept-Encoding": "gzip, deflate"}
        cik_digits = re.sub(r"\D", "", str(cik or ""))
        if not cik_digits:
            cik_digits = self._resolve_cik(symbol, headers=headers)
        cik_padded = cik_digits.zfill(10)
        run = self.store.create_research_run(
            slice_id="official-sec",
            universe_scope=symbol,
            as_of=cutoff,
            input_manifest={"ticker": symbol, "cik": cik_padded, "forms": list(forms), "limit": limit},
            model_version="official-source-v1",
            prompt_version="none",
        )
        submissions_url = f"{SEC_DATA}/submissions/CIK{cik_padded}.json"
        payload = self._json(self._get(submissions_url, headers=headers))
        recent = ((payload.get("filings") or {}).get("recent") or {})
        accessions = recent.get("accessionNumber") or []
        rows: list[dict[str, Any]] = []
        for index, accession in enumerate(accessions):
            def field(name: str) -> str:
                values = recent.get(name) or []
                return str(values[index] or "") if index < len(values) else ""

            form = field("form")
            filing_date = _date_prefix(field("filingDate"))
            accepted = field("acceptanceDateTime")
            available_date = _date_prefix(accepted or filing_date)
            primary = posixpath.basename(field("primaryDocument"))
            if form not in forms or not filing_date or available_date > cutoff or not primary:
                continue
            accession_text = str(accession)
            accession_clean = re.sub(r"\D", "", accession_text)
            if not accession_clean:
                continue
            filing_url = (
                f"{SEC_WWW}/Archives/edgar/data/{int(cik_padded)}/"
                f"{accession_clean}/{quote(primary)}"
            )
            filing_response = self._get(filing_url, headers=headers)
            document, created = self.store.add_document(
                content=bytes(filing_response.content),
                title=f"{symbol} {form} {filing_date}",
                source_url=filing_url,
                source_id="sec_edgar",
                media_type=str(filing_response.headers.get("content-type") or "text/html"),
                published_at=filing_date,
                observed_at=cutoff,
                as_of=available_date,
                domain="official_filings",
                metadata={
                    "ticker": symbol,
                    "cik": cik_padded,
                    "accession": accession_text,
                    "form": form,
                    "filing_date": filing_date,
                    "report_date": _date_prefix(field("reportDate")),
                    "available_date": available_date,
                    "primary_document": primary,
                    "amendment": form.endswith("/A"),
                    "company_impact_claimed": False,
                },
                suffix=".txt",
            )
            rows.append({"document": document, "created": created})
            if len(rows) >= max(1, min(int(limit), 200)):
                break
        self.store.upsert_source_coverage(
            run_id=run["id"],
            source_id="sec_edgar",
            coverage_date=cutoff,
            retrieved=len(rows),
            status="partial" if rows else "unknown",
            details={
                "submissions_url": submissions_url,
                "forms": list(forms),
                "recent_feed_only": True,
                "company_impact_claimed": False,
            },
        )
        finished = self.store.finish_research_run(
            run["id"], status="complete" if rows else "degraded"
        )
        return {
            "run": finished,
            "ticker": symbol,
            "cik": cik_padded,
            "as_of": cutoff,
            "filings": rows,
            "coverage_complete": False,
            "claims_created": 0,
            "orders_generated": False,
        }

    def sync_federal_register(
        self,
        query: str,
        *,
        as_of: str = "",
        limit: int = 40,
    ) -> dict:
        term = str(query or "").strip()
        if len(term) < 3:
            raise ValueError("policy query must contain at least 3 characters")
        cutoff = _cutoff(as_of)
        run = self.store.create_research_run(
            slice_id="official-policy",
            universe_scope=term,
            as_of=cutoff,
            input_manifest={"source": "federal_register", "query": term, "limit": limit},
            model_version="official-source-v1",
            prompt_version="none",
        )
        response = self._get(
            f"{FEDERAL_REGISTER_API}/documents.json",
            params={
                "conditions[term]": term,
                "per_page": max(1, min(int(limit), 1000)),
                "order": "newest",
            },
        )
        payload = self._json(response)
        rows = []
        for item in payload.get("results") or []:
            if not isinstance(item, dict):
                continue
            publication_date = str(item.get("publication_date") or "")[:10]
            if not publication_date or publication_date > cutoff:
                continue
            effective_on = str(item.get("effective_on") or "")[:10]
            document_number = str(item.get("document_number") or "")
            source_url = str(item.get("html_url") or "")
            state = _policy_state(
                str(item.get("type") or ""), publication_date, effective_on, cutoff
            )
            immutable = json.dumps(item, ensure_ascii=False, sort_keys=True).encode("utf-8")
            document, created = self.store.add_document(
                content=immutable,
                title=str(item.get("title") or document_number),
                source_url=source_url,
                source_id="federal_register",
                media_type="application/json",
                published_at=publication_date,
                observed_at=cutoff,
                as_of=publication_date,
                domain="official_policy",
                metadata={
                    "document_number": document_number,
                    "document_type": str(item.get("type") or ""),
                    "publication_date": publication_date,
                    "effective_on": effective_on,
                    "policy_state": state,
                    "query": term,
                    "company_impact_claimed": False,
                },
                suffix=".json",
            )
            rows.append({"document": document, "created": created, "policy_state": state})
        self.store.upsert_source_coverage(
            run_id=run["id"],
            source_id="federal_register",
            coverage_date=cutoff,
            retrieved=len(rows),
            status="partial" if rows else "unknown",
            details={"query": term, "result_count": int(payload.get("count") or 0),
                     "company_impact_claimed": False},
        )
        finished = self.store.finish_research_run(
            run["id"], status="complete" if rows else "degraded"
        )
        return {
            "run": finished,
            "query": term,
            "as_of": cutoff,
            "documents": rows,
            "coverage_complete": False,
            "claims_created": 0,
            "orders_generated": False,
        }

    def _api_key(self, supplied: str, config_name: str, label: str) -> str:
        value = str(supplied or self.config.get(config_name, "") or "").strip()
        if not value:
            raise ValueError(f"{label} sync requires API key")
        return value

    def sync_congress_bill(
        self,
        *,
        congress: int,
        bill_type: str,
        bill_number: int,
        api_key: str = "",
        as_of: str = "",
    ) -> dict:
        cutoff = _cutoff(as_of)
        congress_no = int(congress)
        number = int(bill_number)
        kind = str(bill_type or "").lower().strip()
        if not 1 <= congress_no <= 999 or not 1 <= number or not re.fullmatch(r"[a-z]{1,8}", kind):
            raise ValueError("invalid Congress bill identifier")
        key = self._api_key(api_key, "congress_api_key", "Congress.gov")
        url = f"{CONGRESS_API}/bill/{congress_no}/{kind}/{number}"
        payload = self._json(self._get(url, params={"api_key": key, "format": "json"}))
        bill = payload.get("bill") or {}
        updated = _date_prefix(str(bill.get("updateDate") or ""))
        pit_eligible = bool(updated) and updated <= cutoff
        run = self.store.create_research_run(
            slice_id="official-policy",
            universe_scope=f"{congress_no}-{kind}-{number}",
            as_of=cutoff,
            input_manifest={"source": "congress_gov", "url": url, "updated": updated},
            model_version="official-source-v1",
            prompt_version="none",
        )
        rows = []
        if pit_eligible:
            source_url = str(bill.get("url") or url)
            document, created = self.store.add_document(
                content=json.dumps(bill, ensure_ascii=False, sort_keys=True).encode("utf-8"),
                title=str(bill.get("title") or f"{congress_no} {kind.upper()} {number}"),
                source_url=source_url,
                source_id="congress_gov",
                media_type="application/json",
                published_at=_date_prefix(str(bill.get("introducedDate") or "")),
                observed_at=cutoff,
                as_of=updated,
                domain="official_policy",
                metadata={
                    "congress": congress_no, "bill_type": kind, "bill_number": number,
                    "update_date": updated, "latest_action": bill.get("latestAction") or {},
                    "policy_state": "latest_action_as_reported",
                    "company_impact_claimed": False,
                },
                suffix=".json",
            )
            rows.append({"document": document, "created": created})
        self.store.upsert_source_coverage(
            run_id=run["id"], source_id="congress_gov", coverage_date=cutoff,
            retrieved=len(rows), index_only=0 if pit_eligible else 1,
            status="partial" if rows else "index_only",
            details={"url": url, "updated": updated, "pit_eligible": pit_eligible},
        )
        finished = self.store.finish_research_run(
            run["id"], status="complete" if rows else "degraded"
        )
        return {"run": finished, "documents": rows, "pit_eligible": pit_eligible,
                "claims_created": 0, "orders_generated": False}

    def sync_regulations(
        self,
        query: str,
        *,
        api_key: str = "",
        as_of: str = "",
        limit: int = 40,
    ) -> dict:
        term = str(query or "").strip()
        if len(term) < 3:
            raise ValueError("regulations query must contain at least 3 characters")
        cutoff = _cutoff(as_of)
        key = self._api_key(api_key, "regulations_api_key", "Regulations.gov")
        url = f"{REGULATIONS_API}/documents"
        payload = self._json(self._get(
            url,
            headers={"X-Api-Key": key},
            params={"filter[searchTerm]": term, "page[size]": max(1, min(int(limit), 250)),
                    "sort": "-postedDate"},
        ))
        run = self.store.create_research_run(
            slice_id="official-policy", universe_scope=term, as_of=cutoff,
            input_manifest={"source": "regulations_gov", "query": term, "limit": limit},
            model_version="official-source-v1", prompt_version="none",
        )
        rows = []
        excluded = 0
        for item in payload.get("data") or []:
            attributes = item.get("attributes") or {} if isinstance(item, dict) else {}
            posted = _date_prefix(str(attributes.get("postedDate") or ""))
            modified = _date_prefix(str(attributes.get("lastModifiedDate") or posted))
            if not posted or posted > cutoff or (modified and modified > cutoff):
                excluded += 1
                continue
            document_id = str(item.get("id") or "")
            document, created = self.store.add_document(
                content=json.dumps(item, ensure_ascii=False, sort_keys=True).encode("utf-8"),
                title=str(attributes.get("title") or document_id),
                source_url=f"https://www.regulations.gov/document/{quote(document_id)}",
                source_id="regulations_gov", media_type="application/json",
                published_at=posted, observed_at=cutoff, as_of=modified or posted,
                domain="official_policy",
                metadata={
                    "document_id": document_id, "docket_id": attributes.get("docketId") or "",
                    "document_type": attributes.get("documentType") or "",
                    "posted_date": posted, "last_modified_date": modified,
                    "withdrawn": bool(attributes.get("withdrawn")),
                    "policy_state": "withdrawn" if attributes.get("withdrawn") else "posted",
                    "company_impact_claimed": False,
                },
                suffix=".json",
            )
            rows.append({"document": document, "created": created})
        self.store.upsert_source_coverage(
            run_id=run["id"], source_id="regulations_gov", coverage_date=cutoff,
            retrieved=len(rows), index_only=excluded,
            status="partial" if rows else "unknown",
            details={"query": term, "future_or_modified_after_cutoff": excluded},
        )
        finished = self.store.finish_research_run(
            run["id"], status="complete" if rows else "degraded"
        )
        return {"run": finished, "documents": rows, "pit_excluded": excluded,
                "claims_created": 0, "orders_generated": False}
