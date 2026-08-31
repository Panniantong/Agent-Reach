# -*- coding: utf-8 -*-
"""Versioned industry research packs built on the narrative evidence ledger.

The module is recommend-only, point-in-time, and read-only with respect to Quant.
Static theme definitions are research blueprints tagged FRAME/GUESS, never evidence.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from agent_reach.config import Config
from agent_reach.narrative.models import utc_now
from agent_reach.narrative.quant import QuantAdapter
from agent_reach.narrative.store import NarrativeStore

RESEARCH_MODEL_VERSION = "industry-research-v0.4"
METHOD_PROMPT_VERSION = "serenity-method-v1"
SERENITY_SOURCE_ID = "serenity_aleabitoreddit"
SERENITY_HANDLE = "aleabitoreddit"


THEMES: dict[str, dict[str, Any]] = {
    "cpo-external-laser": {
        "title": "CPO external light source",
        "phase": "1A",
        "universe_scope": "cpo_external_laser",
        "system_change": "AI scale-up fabrics face copper reach and power constraints.",
        "constraint_type": "hardware",
        "constraint_statement": "CPO moves optics next to the switch while qualified lasers remain external.",
        "scarce_layer": "Qualified external InP laser sources for CPO engines",
        "measurement_contract": {
            "supply": "qualified ELS suppliers and laser-grade capacity",
            "load": "CPO qualification and shipment demand",
            "watch": ["qualification language", "laser-line capacity", "InP lead time"],
        },
        "tickers": ["LITE", "COHR", "AAOI", "SIVE.ST"],
        "nodes": [
            ("demand", "DemandDriver", "AI rack scale-up bandwidth", []),
            ("cpo", "Technology", "Co-packaged optics", []),
            ("els", "Component", "External light source", ["LITE", "COHR", "AAOI", "SIVE.ST"]),
            ("inp", "Material", "Laser-grade InP", ["AXTI", "IQE", "5802.T"]),
        ],
        "edges": [
            ("demand", "cpo", "causal_hypothesis"),
            ("cpo", "els", "physical_dependency"),
            ("els", "inp", "physical_dependency"),
        ],
        "next_move": "Read official CPO qualification language and cross-check laser capacity against InP lead times.",
        "failure_conditions": [
            "CPO qualification does not convert into disclosed shipments.",
            "Alternative laser architecture removes the external-source dependency.",
            "No official evidence connects capacity constraints to revenue, margin, or delivery.",
        ],
        "policy_exposure": ["US export controls", "CHIPS Act manufacturing incentives"],
        "historical_analogues": ["technology_diffusion_capacity"],
    },
    "inp-substrate": {
        "title": "InP substrate",
        "phase": "1B",
        "universe_scope": "inp_substrate",
        "system_change": "CPO and datacom lasers increase demand for laser-grade indium phosphide.",
        "constraint_type": "hardware",
        "constraint_statement": "Boule growth, defect density, wafer-size transition, and qualification limit substitution.",
        "scarce_layer": "Merchant laser-grade InP substrate supply",
        "measurement_contract": {
            "supply": "qualified merchant substrate suppliers and boule capacity",
            "load": "laser and epi wafer starts",
            "watch": ["defect density", "4-to-6-inch transition", "qualification tenure"],
        },
        "tickers": ["AXTI", "IQE", "5802.T", "LITE", "COHR"],
        "nodes": [
            ("laser", "Component", "InP laser devices", ["LITE", "COHR"]),
            ("epi", "Material", "InP epitaxy", ["IQE"]),
            ("substrate", "Material", "Laser-grade InP substrate", ["AXTI", "5802.T"]),
        ],
        "edges": [
            ("laser", "epi", "physical_dependency"),
            ("epi", "substrate", "physical_dependency"),
        ],
        "next_move": "Map who is qualified on larger laser-grade wafers instead of relying on expansion announcements.",
        "failure_conditions": [
            "Captive substrate capacity replaces merchant demand.",
            "Defect or qualification data do not support a persistent constraint.",
        ],
        "policy_exposure": ["critical semiconductor material controls"],
        "historical_analogues": ["technology_diffusion_capacity"],
    },
    "eda-bridge": {
        "title": "EDA bridge",
        "phase": "2E",
        "universe_scope": "eda_software",
        "system_change": "Leading-edge digital, photonics, and 3D packaging depend on foundry-qualified design flows.",
        "constraint_type": "software",
        "constraint_statement": "PDK recertification and signoff switching costs constrain substitution.",
        "scarce_layer": "Foundry-qualified EDA and PDK control planes",
        "measurement_contract": {
            "supply": "independent tool graphs that can close a qualified tape-out",
            "load": "advanced-node, photonic, and 3D design starts",
            "watch": ["PDK releases", "backlog", "China revenue mix", "signoff qualification"],
        },
        "tickers": ["SNPS", "CDNS"],
        "nodes": [
            ("foundry", "Company", "Leading-edge foundries", ["TSM", "INTC"]),
            ("pdk", "Technology", "Foundry-qualified PDK", []),
            ("eda", "Product", "EDA signoff tool graph", ["SNPS", "CDNS"]),
        ],
        "edges": [
            ("foundry", "pdk", "physical_dependency"),
            ("pdk", "eda", "physical_dependency"),
        ],
        "next_move": "Read foundry PDK releases and company backlog/concentration disclosures.",
        "failure_conditions": [
            "Open or internal flows reduce PDK recertification costs.",
            "Backlog fails to convert or export restrictions dominate demand.",
        ],
        "policy_exposure": ["EDA export controls", "China technology restrictions"],
        "historical_analogues": ["technology_diffusion_capacity", "regulation_geopolitics"],
    },
    "security-control-plane": {
        "title": "Security control plane",
        "phase": "2A",
        "universe_scope": "security_control_plane",
        "system_change": "Agentic workloads increase telemetry, identity, and compliance surface area.",
        "constraint_type": "software",
        "constraint_statement": "Compliance walls, switching cost, and installed telemetry limit substitutable control planes.",
        "scarce_layer": "Certified security control planes with high conversion cost",
        "measurement_contract": {
            "supply": "substitutable certified control planes",
            "load": "identity, endpoint, and cloud telemetry growth",
            "watch": ["RPO/cRPO", "government mix", "retention", "SBC/revenue", "certification"],
        },
        "tickers": ["PANW", "CRWD", "FTNT", "ZS"],
        "nodes": [
            ("identity", "Technology", "Identity and zero-trust control", ["PANW"]),
            ("endpoint", "Technology", "Endpoint telemetry control", ["CRWD"]),
            ("network", "Technology", "Network security estate", ["FTNT"]),
            ("cloud", "Technology", "Cloud security control", ["ZS"]),
            ("compliance", "Policy", "Government compliance wall", []),
        ],
        "edges": [
            ("compliance", "identity", "policy_exposure"),
            ("compliance", "endpoint", "policy_exposure"),
            ("identity", "cloud", "causal_hypothesis"),
        ],
        "next_move": "Extract RPO, government mix, retention, and conversion evidence from official filings.",
        "failure_conditions": [
            "Platform consolidation does not improve disclosed conversion metrics.",
            "Control planes remain readily substitutable after compliance qualification.",
        ],
        "policy_exposure": ["FedRAMP", "federal cybersecurity procurement"],
        "historical_analogues": ["technology_diffusion_capacity", "regulation_geopolitics"],
    },
}


METHOD_DIMENSIONS = {
    "demand_certainty": "What observable demand is forcing adoption?",
    "substitutability": "How many qualified substitutes exist at the same specification?",
    "capacity_lead_time": "How long does physical or organizational capacity take to add?",
    "qualification_lead_time": "How long does customer or regulator qualification take?",
    "pricing_power": "Can the constrained layer retain economics rather than pass them through?",
    "value_capture": "Which layer converts the constraint into revenue, margin, or cash flow?",
    "policy_exposure": "Which enacted or proposed policy changes the path?",
    "rerating_catalyst": "What observable event could close the valuation gap?",
    "counterevidence": "What evidence would weaken or falsify the thesis?",
}

METHOD_SIGNAL_TERMS = {
    "demand_certainty": ("需求", "訂單", "出貨", "backlog", "demand", "shipment", "rpo"),
    "substitutability": ("替代", "供應商", "second source", "substitute", "supplier"),
    "capacity_lead_time": ("產能", "擴產", "交期", "capacity", "lead time", "fab"),
    "qualification_lead_time": ("認證", "驗證", "qualification", "qualified", "certification"),
    "pricing_power": ("漲價", "價格權", "asp", "pricing", "price increase"),
    "value_capture": ("毛利", "現金流", "營收", "margin", "cash flow", "revenue"),
    "policy_exposure": ("法案", "補貼", "禁令", "監管", "policy", "act", "regulation", "export control"),
    "rerating_catalyst": ("催化", "重估", "量產", "catalyst", "rerating", "ramp"),
    "counterevidence": ("風險", "失效", "不成立", "risk", "invalid", "failure", "counter"),
}

METHOD_STAGES = (
    {
        "id": "forcing_function",
        "label": "System pressure / demand forcing",
        "dimensions": ("demand_certainty", "policy_exposure"),
        "minimum_joint_dimensions": 2,
        "question": "Which observable demand or policy change is forcing adoption?",
    },
    {
        "id": "constraint_test",
        "label": "Constraint and substitution test",
        "dimensions": (
            "substitutability",
            "capacity_lead_time",
            "qualification_lead_time",
        ),
        "minimum_joint_dimensions": 2,
        "question": "What cannot be substituted or expanded on the demand timeline?",
    },
    {
        "id": "value_capture_test",
        "label": "Value-capture test",
        "dimensions": ("pricing_power", "value_capture"),
        "minimum_joint_dimensions": 2,
        "question": "Does the constrained layer retain economics in operating data?",
    },
    {
        "id": "resolution_test",
        "label": "Catalyst and falsification test",
        "dimensions": ("rerating_catalyst", "counterevidence"),
        "minimum_joint_dimensions": 2,
        "question": "What observable event closes the gap, and what would invalidate it?",
    },
)

THEME_SIGNAL_TERMS = {
    "cpo-external-laser": ("cpo", "co-packaged optics", "external light", "外置雷射", "外部光源"),
    "inp-substrate": ("inp", "indium phosphide", "磷化銦", "基板", "substrate"),
    "eda-bridge": ("eda", "pdk", "signoff", "tapeout", "tape-out", "流片"),
    "security-control-plane": ("cybersecurity", "資安", "zero trust", "endpoint", "fedramp"),
}


def _parse_timestamp(value: str) -> Optional[datetime]:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _stable(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _known_tickers() -> set[str]:
    return {ticker for theme in THEMES.values() for ticker in theme["tickers"]}


def extract_tickers(text: str) -> list[str]:
    """Conservative extraction: cash-tags plus exact known-universe symbols."""
    upper = str(text or "").upper()
    found = {match.group(1) for match in re.finditer(r"\$([A-Z][A-Z0-9.-]{0,9})\b", upper)}
    for ticker in _known_tickers():
        if re.search(rf"(?<![A-Z0-9]){re.escape(ticker)}(?![A-Z0-9])", upper):
            found.add(ticker)
    return sorted(found)


def _literal_signal_matches(text: str, terms: tuple[str, ...]) -> list[str]:
    lowered = str(text or "").casefold()
    matches = set()
    for term in terms:
        normalized = term.casefold()
        if re.fullmatch(r"[a-z0-9][a-z0-9.-]*", normalized):
            if re.search(
                rf"(?<![a-z0-9]){re.escape(normalized)}(?![a-z0-9])",
                lowered,
            ):
                matches.add(term)
        elif normalized in lowered:
            matches.add(term)
    return sorted(matches)


def draft_thesis_unit(text: str, observed_at: str) -> dict:
    """Extract only literal signals; leave causal fields empty for human/LLM review."""
    tickers = extract_tickers(text)
    themes = []
    for slice_id, terms in THEME_SIGNAL_TERMS.items():
        ticker_overlap = set(tickers) & set(THEMES[slice_id]["tickers"])
        matches = _literal_signal_matches(text, terms)
        if ticker_overlap or matches:
            themes.append(
                {
                    "slice": slice_id,
                    "ticker_matches": sorted(ticker_overlap),
                    "literal_matches": matches,
                    "tag": "FRAME",
                    "confidence": "LOW",
                }
            )
    method_signals = {
        dimension: matches
        for dimension, terms in METHOD_SIGNAL_TERMS.items()
        if (matches := _literal_signal_matches(text, terms))
    }
    return {
        "observed_at": observed_at,
        "themes": themes,
        "tickers": tickers,
        "system_change": "",
        "scarce_layer": "",
        "value_chain_role": "",
        "claim": str(text or ""),
        "time_horizon": "",
        "supporting_indicators": [],
        "failure_conditions": [],
        "catalysts": [],
        "method_signals": method_signals,
        "source_excerpt": str(text or "")[:1000],
        "extraction_status": "literal_signals_pending_review",
        "tag": "GUESS",
        "confidence": "LOW",
    }


class ResearchService:
    """Builds immutable research packs without allowing an LLM into KPI paths."""

    def __init__(
        self,
        store: Optional[NarrativeStore] = None,
        quant: Optional[QuantAdapter] = None,
        config: Optional[Config] = None,
    ):
        self.store = store or NarrativeStore(config=config)
        self.quant = quant or QuantAdapter(config=config)
        self.config = config or Config()

    def themes(self) -> list[dict]:
        latest_by_slice: dict[str, dict] = {}
        for pack in self.store.list_research_packs(limit=1000):
            latest_by_slice.setdefault(pack["slice"], pack)
        return [
            {
                "id": slice_id,
                "title": theme["title"],
                "phase": theme["phase"],
                "universe_scope": theme["universe_scope"],
                "scarce_layer": theme["scarce_layer"],
                "tickers": theme["tickers"],
                "latest_pack": latest_by_slice.get(slice_id),
                "blueprint_tag": "FRAME",
                "blueprint_confidence": "LOW",
            }
            for slice_id, theme in THEMES.items()
        ]

    def _all_serenity_units(self) -> list[dict]:
        rows = []
        blob_root = self.store.blob_dir.resolve()
        for document in self.store.list_documents(limit=5000):
            if document.get("source_id") != SERENITY_SOURCE_ID:
                continue
            path = Path(str(document.get("blob_path") or "")).resolve()
            try:
                path.relative_to(blob_root)
            except ValueError:
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(payload, dict) or "original" not in payload:
                continue
            metadata = document.get("metadata") or {}
            rows.append(
                {
                    "document_id": document["id"],
                    "source_url": document.get("source_url") or "",
                    "published_at": document.get("published_at") or "",
                    "original": str(payload.get("original") or ""),
                    "zh_hant": str(payload.get("zh_hant") or ""),
                    "en": str(payload.get("en") or ""),
                    "translation_status": str(payload.get("translation_status") or "pending"),
                    "source_language": str(payload.get("source_language") or "und"),
                    "original_text_verified": bool(
                        metadata.get("original_text_verified", False)
                    ),
                    "images": [
                        str(value) for value in (metadata.get("images") or []) if value
                    ],
                    "thesis_unit": payload.get("thesis_unit") or {},
                }
            )
        rows.sort(key=lambda row: (row["published_at"], row["document_id"]), reverse=True)
        return rows

    def serenity_units(self, *, limit: int = 100) -> list[dict]:
        rows = self._all_serenity_units()
        return rows[: max(1, min(int(limit), 1000))]

    def serenity_export(self, *, days: int = 90, as_of: str = "") -> dict:
        if not 1 <= int(days) <= 3650:
            raise ValueError("days must be between 1 and 3650")
        try:
            end = date.fromisoformat((as_of or date.today().isoformat())[:10])
        except ValueError as exc:
            raise ValueError("as_of must be an ISO date") from exc
        start = end - timedelta(days=int(days) - 1)
        units = [
            row for row in self._all_serenity_units()
            if start.isoformat()
            <= str(row.get("published_at") or "")[:10]
            <= end.isoformat()
        ]
        from agent_reach.narrative.serenity_export import render_serenity_archive

        rendered = render_serenity_archive(
            units,
            handle=SERENITY_HANDLE,
            as_of=end.isoformat(),
            title_suffix=f" · {days}D",
        )
        return {
            **rendered,
            "as_of": end.isoformat(),
            "from_date": start.isoformat(),
            "days": int(days),
            "archive_complete": False,
        }

    def method_profile(
        self,
        *,
        as_of: str,
        evidence_claim_ids: Optional[list[str]] = None,
        observations: Optional[dict[str, dict]] = None,
        signature_signals: Optional[list] = None,
    ) -> dict:
        observed_dimensions = {
            name: {
                "definition": definition,
                **((observations or {}).get(name) or {
                    "observed_count": 0,
                    "literal_terms": [],
                    "repeated_in_independent_posts": False,
                }),
                "rule_status": "candidate_pending_human_review",
            }
            for name, definition in METHOD_DIMENSIONS.items()
        }
        profile, created = self.store.add_method_profile(
            source_id=SERENITY_SOURCE_ID,
            name="Serenity bottleneck research method",
            as_of=as_of,
            dimensions=observed_dimensions,
            signature_signals=signature_signals or [],
            invalidators=[
                "no official or Quant measurement for the claimed bottleneck",
                "qualified substitutes expand faster than demand load",
                "constraint does not convert into financial value capture",
            ],
            evidence_claim_ids=evidence_claim_ids or [],
            status="draft",
        )
        return {"profile": profile, "created": created, "voting_weight": None}

    def serenity_methodology(
        self,
        *,
        as_of: str = "",
        min_independent_posts: int = 2,
        persist: bool = True,
    ) -> dict:
        """Build a source-grounded method profile from the complete local corpus.

        Literal dimensions and co-occurrences are computed. The proposed stage
        order remains an explicit FRAME: bag-of-words evidence cannot establish
        that Serenity applies the stages causally or in that order.
        """

        if not 2 <= int(min_independent_posts) <= 20:
            raise ValueError("min_independent_posts must be between 2 and 20")
        resolved_as_of = (as_of or date.today().isoformat())[:10]
        units = [
            row for row in self._all_serenity_units()
            if str(row.get("published_at") or "")[:10] <= resolved_as_of
        ]
        by_document: dict[str, dict[str, Any]] = {}
        dimension_posts: dict[str, set[str]] = {
            name: set() for name in METHOD_DIMENSIONS
        }
        dimension_terms: dict[str, set[str]] = {
            name: set() for name in METHOD_DIMENSIONS
        }
        dimension_evidence: dict[str, list[dict]] = {
            name: [] for name in METHOD_DIMENSIONS
        }
        ticker_counts: Counter[str] = Counter()
        theme_counts: Counter[str] = Counter()
        configured_theme_documents = 0
        for row in units:
            unit = draft_thesis_unit(
                str(row.get("original") or ""),
                str(row.get("published_at") or ""),
            )
            signals = unit["method_signals"]
            ticker_counts.update(unit["tickers"])
            slices = {theme["slice"] for theme in unit["themes"]}
            theme_counts.update(slices)
            configured_theme_documents += int(bool(slices))
            document_id = str(row["document_id"])
            by_document[document_id] = {
                "dimensions": set(signals),
                "source_url": row.get("source_url") or "",
                "published_at": row.get("published_at") or "",
            }
            for dimension, terms in signals.items():
                dimension_posts[dimension].add(document_id)
                dimension_terms[dimension].update(terms)
                dimension_evidence[dimension].append(
                    {
                        "document_id": document_id,
                        "source_url": row.get("source_url") or "",
                        "published_at": row.get("published_at") or "",
                        "literal_terms": terms,
                        "excerpt": str(row.get("original") or "")[:280],
                    }
                )

        observations = {}
        for name in METHOD_DIMENSIONS:
            evidence = sorted(
                dimension_evidence[name],
                key=lambda row: (row["published_at"], row["document_id"]),
                reverse=True,
            )
            observations[name] = {
                "observed_count": len(dimension_posts[name]),
                "literal_terms": sorted(dimension_terms[name]),
                "repeated_in_independent_posts": (
                    len(dimension_posts[name]) >= int(min_independent_posts)
                ),
                "evidence_posts": evidence[:20],
                "evidence_truncated": len(evidence) > 20,
                "observation_tag": "COMPUTED",
                "observation_confidence": "HIGH",
            }

        stage_rows = []
        inferred_signals = []
        for stage in METHOD_STAGES:
            dimensions = set(stage["dimensions"])
            supporting = []
            for document_id, row in by_document.items():
                matched = sorted(dimensions & row["dimensions"])
                if len(matched) >= int(stage["minimum_joint_dimensions"]):
                    supporting.append(
                        {
                            "document_id": document_id,
                            "source_url": row["source_url"],
                            "published_at": row["published_at"],
                            "matched_dimensions": matched,
                        }
                    )
            supporting.sort(
                key=lambda row: (row["published_at"], row["document_id"]),
                reverse=True,
            )
            repeated = len(supporting) >= int(min_independent_posts)
            stage_row = {
                **stage,
                "dimensions": list(stage["dimensions"]),
                "joint_post_count": len(supporting),
                "repeated_in_independent_posts": repeated,
                "evidence_posts": supporting[:20],
                "status": (
                    "candidate_pending_human_review" if repeated else "insufficient_data"
                ),
                "tag": "INFERRED" if repeated else "FRAME",
                "confidence": "LOW",
            }
            stage_rows.append(stage_row)
            if repeated:
                inferred_signals.append(
                    {
                        "stage": stage["id"],
                        "statement": stage["question"],
                        "joint_post_count": len(supporting),
                        "tag": "INFERRED",
                        "confidence": "LOW",
                    }
                )

        cooccurrence = []
        names = list(METHOD_DIMENSIONS)
        for index, left in enumerate(names):
            for right in names[index + 1:]:
                shared = dimension_posts[left] & dimension_posts[right]
                if len(shared) >= int(min_independent_posts):
                    cooccurrence.append(
                        {
                            "dimensions": [left, right],
                            "independent_post_count": len(shared),
                            "tag": "COMPUTED",
                            "confidence": "HIGH",
                        }
                    )
        cooccurrence.sort(
            key=lambda row: (-row["independent_post_count"], row["dimensions"])
        )

        claims_by_document: dict[str, list[str]] = {}
        for claim in self.store.list_claims(domain="serenity_method", limit=1000):
            claims_by_document.setdefault(str(claim["document_id"]), []).append(claim["id"])
        evidence_claim_ids = sorted({
            claim_id
            for document_id in by_document
            for claim_id in claims_by_document.get(document_id, [])
        })
        profile = None
        if persist:
            profile = self.method_profile(
                as_of=resolved_as_of,
                evidence_claim_ids=evidence_claim_ids,
                observations=observations,
                signature_signals=inferred_signals,
            )
        return {
            "as_of": resolved_as_of,
            "source_id": SERENITY_SOURCE_ID,
            "corpus": {
                "independent_documents": len(by_document),
                "archive_complete": False,
                "zero_means_unknown": True,
                "ticker_counts": dict(sorted(
                    ticker_counts.items(), key=lambda pair: (-pair[1], pair[0])
                )[:50]),
                "configured_theme_counts": dict(sorted(
                    theme_counts.items(), key=lambda pair: (-pair[1], pair[0])
                )),
                "configured_theme_documents": configured_theme_documents,
                "unclassified_theme_documents": (
                    len(by_document) - configured_theme_documents
                ),
                "theme_scope": "configured research themes only; unclassified is not no topic",
            },
            "dimensions": observations,
            "candidate_logic": stage_rows,
            "cooccurrence": cooccurrence,
            "sequence_status": "not_established_by_literal_cooccurrence",
            "method_profile": profile,
            "voting_weight": None,
            "orders_generated": False,
        }

    def serenity_backfill(
        self,
        *,
        days: int = 90,
        count: int = 2000,
        translations: Optional[dict[str, dict[str, str]]] = None,
        fetcher: Optional[Callable[[str, int, Config], list[Any]]] = None,
        source_jsonl: Optional[Path | str] = None,
    ) -> dict:
        if not 1 <= int(days) <= 3650:
            raise ValueError("days must be between 1 and 3650")
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=int(days))
        archive_items: list[Any] = []
        archive_manifest: dict[str, Any] = {}
        merged_translations = dict(translations or {})
        if source_jsonl:
            from agent_reach.narrative.serenity_source import load_x_subs_jsonl

            archive = load_x_subs_jsonl(source_jsonl, max_records=max(1, int(count)))
            archive_items = archive.items
            archive_manifest = archive.manifest
            merged_translations = {**archive.translations, **merged_translations}
        sources = [f"twitter:@{SERENITY_HANDLE}"]
        if archive_manifest:
            sources.append("x_subs_downloader:posts.jsonl")
        run = self.store.create_research_run(
            slice_id="serenity-method",
            universe_scope="all_original_topics",
            as_of=now.date().isoformat(),
            input_manifest={
                "sources": sources,
                "days": int(days),
                "requested_count": int(count),
                "pure_reposts_excluded": True,
                "archive_completeness_claimed": False,
                "x_subs_archive": archive_manifest,
            },
            model_version=RESEARCH_MODEL_VERSION,
            prompt_version=METHOD_PROMPT_VERSION,
        )
        if fetcher is None:
            from agent_reach.radar_backfill import backfill_twitter

            fetcher = backfill_twitter
        fetch_error = ""
        try:
            items = fetcher(SERENITY_HANDLE, int(count), self.config)
        except Exception as exc:  # noqa: BLE001
            items = []
            fetch_error = str(exc)[:500]
        items = list(items or []) + archive_items
        eligible = []
        for item in items:
            published = _parse_timestamp(item.ts or "")
            if published is None or published < cutoff or published > now:
                continue
            if bool((item.extra or {}).get("isRetweet")):
                continue
            eligible.append((published, item))
        eligible.sort(key=lambda pair: pair[0])

        seen: set[str] = set()
        retrieved_by_day: Counter[str] = Counter()
        duplicate_by_day: Counter[str] = Counter()
        document_ids: list[str] = []
        claim_ids: list[str] = []
        for published, item in eligible:
            key = item.url or hashlib.sha256(item.text.encode("utf-8")).hexdigest()
            day = published.date().isoformat()
            if key in seen:
                duplicate_by_day[day] += 1
                continue
            seen.add(key)
            retrieved_by_day[day] += 1
            supplied = merged_translations.get(item.url) or {}
            translated_zh = str(supplied.get("zh_hant") or "")
            translated_en = str(supplied.get("en") or "")
            thesis_unit = draft_thesis_unit(item.text, published.isoformat())
            tickers = thesis_unit["tickers"]
            source_language = str((item.extra or {}).get("sourceLanguage") or "und")
            body = {
                "original": item.text,
                "zh_hant": translated_zh,
                "en": translated_en,
                "source_language": source_language,
                "translation_status": "complete" if translated_zh and translated_en else "pending",
                "thesis_unit": thesis_unit,
            }
            document, created = self.store.add_document(
                content=_stable(body).encode("utf-8"),
                title=item.title,
                source_url=item.url,
                source_id=SERENITY_SOURCE_ID,
                media_type="application/json",
                published_at=published.isoformat(),
                observed_at=utc_now(),
                as_of=published.isoformat(),
                domain="serenity_method",
                metadata={
                    "platform": "twitter",
                    "handle": SERENITY_HANDLE,
                    "tickers": tickers,
                    "translation_status": body["translation_status"],
                    "original_only": True,
                    "backend": str((item.extra or {}).get("backend") or "twitter-cli"),
                    "subscriber_only": bool((item.extra or {}).get("subscriberOnly")),
                    "images": (item.extra or {}).get("images") or [],
                    "source_language": source_language,
                    "original_text_verified": bool(
                        (item.extra or {}).get("originalTextVerified", True)
                    ),
                },
                suffix=".json",
            )
            document_ids.append(document["id"])
            if created:
                for ticker in tickers or [""]:
                    claim = self.store.add_claim(
                        document_id=document["id"],
                        text=item.text,
                        excerpt=item.text[:1000],
                        source_id=SERENITY_SOURCE_ID,
                        ticker=ticker,
                        domain="serenity_method",
                        tag="GUESS",
                        confidence="LOW",
                        published_at=published.isoformat(),
                        observed_at=utc_now(),
                        as_of=published.isoformat(),
                        source_url=item.url,
                        evidence=[{"kind": "source_statement", "verified": True, "url": item.url}],
                    )
                    claim_ids.append(claim["id"])

        cursor = cutoff.date()
        while cursor <= now.date():
            day = cursor.isoformat()
            retrieved = retrieved_by_day.get(day, 0)
            rate_limited = int(
                bool(fetch_error)
                and "rate" in fetch_error.casefold()
                and cursor == now.date()
            )
            unavailable = int(
                bool(fetch_error) and not rate_limited and cursor == now.date()
            )
            if rate_limited:
                coverage_status = "rate_limited"
            elif unavailable:
                coverage_status = "unavailable"
            elif retrieved:
                coverage_status = "partial"
            else:
                coverage_status = "unknown"
            self.store.upsert_source_coverage(
                run_id=run["id"],
                source_id=SERENITY_SOURCE_ID,
                coverage_date=day,
                retrieved=retrieved,
                deduplicated=duplicate_by_day.get(day, 0),
                status=coverage_status,
                unavailable=unavailable,
                rate_limited=rate_limited,
                details={
                    "backend": (
                        "twitter-cli user-posts + x_subs_downloader_jsonl"
                        if archive_manifest else "twitter-cli user-posts"
                    ),
                    "archive_complete": False,
                    "meaning": "zero retrieved is unknown, not evidence of zero posts",
                    "fetch_error": fetch_error,
                    "x_subs_archive": archive_manifest,
                },
            )
            cursor += timedelta(days=1)
        methodology = self.serenity_methodology(as_of=now.date().isoformat(), persist=True)
        profile = methodology["method_profile"]
        finished = self.store.finish_research_run(run["id"], status="degraded")
        return {
            "run": finished,
            "handle": SERENITY_HANDLE,
            "cutoff": cutoff.isoformat(),
            "retrieved": sum(retrieved_by_day.values()),
            "deduplicated": sum(duplicate_by_day.values()),
            "documents": sorted(set(document_ids)),
            "claims": claim_ids,
            "coverage_complete": False,
            "fetch_error": fetch_error,
            "source_manifest": archive_manifest,
            "method_profile": profile,
            "methodology": methodology,
            "orders_generated": False,
        }

    @staticmethod
    def _evidence_grade(snapshots: dict[str, dict], verified_claims: list[dict]) -> str:
        covered = sum(
            1 for snapshot in snapshots.values()
            if snapshot["tradingview"].get("status") in {"ok", "degraded"}
            or snapshot["finviz"].get("status") == "ok"
        )
        direct = sum(
            1 for claim in verified_claims
            if any(
                row.get("kind") in {"official", "quant"} and row.get("verified") is True
                for row in claim.get("evidence") or []
            )
        )
        if snapshots and covered == len(snapshots) and direct >= 2:
            return "A"
        if direct >= 1:
            return "B"
        if covered:
            return "C"
        return "E"

    @staticmethod
    def _company_role(theme: dict, ticker: str) -> str:
        roles = [label for _, _, label, tickers in theme["nodes"] if ticker in tickers]
        return " / ".join(roles) if roles else "peer / downstream context"

    def _official_context(self, *, tickers: list[str], as_of: str) -> dict:
        symbols = {ticker.upper() for ticker in tickers}
        filings: dict[str, list[dict]] = {ticker: [] for ticker in tickers}
        policies: list[dict] = []
        for document in self.store.list_documents(limit=5000):
            available = str(document.get("as_of") or document.get("published_at") or "")[:10]
            if not available or available > as_of[:10]:
                continue
            metadata = document.get("metadata") or {}
            if document.get("source_id") == "sec_edgar":
                ticker = str(metadata.get("ticker") or "").upper()
                if ticker in symbols:
                    filings[ticker].append(document)
            elif document.get("source_id") in {
                "congress_gov", "federal_register", "regulations_gov"
            }:
                policies.append(document)
        for rows in filings.values():
            rows.sort(
                key=lambda row: (
                    str((row.get("metadata") or {}).get("available_date") or row.get("as_of")),
                    row["id"],
                ),
                reverse=True,
            )
        policies.sort(key=lambda row: (str(row.get("as_of")), row["id"]), reverse=True)
        return {"filings": filings, "policies": policies}

    def _valuation_rows(
        self,
        *,
        run_id: str,
        theme: dict,
        snapshots: dict[str, dict],
        as_of: str,
    ) -> dict[str, list[dict]]:
        metric = "EV/Sales" if theme["constraint_type"] == "software" else "EV/EBITDA"
        peer_values: list[tuple[str, float]] = []
        for ticker, snapshot in snapshots.items():
            value = (snapshot.get("finviz") or {}).get("row", {}).get(metric)
            if isinstance(value, (int, float)):
                peer_values.append((ticker, float(value)))
        ordered = sorted(value for _, value in peer_values)
        distribution: tuple[Optional[float], Optional[float], Optional[float]] = (None, None, None)
        if len(ordered) >= 3:
            distribution = (
                ordered[max(0, int((len(ordered) - 1) * 0.25))],
                ordered[int((len(ordered) - 1) * 0.50)],
                ordered[min(len(ordered) - 1, int((len(ordered) - 1) * 0.75))],
            )
        out: dict[str, list[dict]] = {}
        for ticker in theme["tickers"]:
            peer = self.store.add_valuation_snapshot(
                run_id=run_id,
                ticker=ticker,
                as_of=as_of,
                method="peer_distribution",
                currency="multiple",
                low=distribution[0],
                mid=distribution[1],
                high=distribution[2],
                assumptions={
                    "metric": metric,
                    "interpretation": "peer multiple dispersion, not a target price",
                    "forced_average": False,
                },
                peers=[{"ticker": peer_ticker, "value": value} for peer_ticker, value in peer_values],
                evidence=[
                    {"kind": "quant", "source": "finviz v151 snapshot", "as_of": as_of}
                ] if peer_values else [],
                status="computed_metric_range" if distribution[0] is not None else "insufficient_data",
            )
            operating = self.store.add_valuation_snapshot(
                run_id=run_id,
                ticker=ticker,
                as_of=as_of,
                method="operating_sensitivity",
                assumptions={
                    "required": theme["measurement_contract"]["watch"],
                    "reason": "capacity/qualification-to-financial sensitivities need reviewed evidence",
                },
                status="insufficient_data",
            )
            dcf = self.store.add_valuation_snapshot(
                run_id=run_id,
                ticker=ticker,
                as_of=as_of,
                method="scenario_dcf",
                assumptions={
                    "required": "reviewed bull/base/bear cash-flow assumptions and event contracts",
                    "forced_average": False,
                },
                status="insufficient_data",
            )
            out[ticker] = [peer, operating, dcf]
        return out

    def run_research(self, slice_id: str, *, as_of: str = "", freeze: bool = True) -> dict:
        theme = THEMES.get(slice_id)
        if theme is None:
            raise LookupError(f"unknown research slice: {slice_id}")
        cutoff = as_of or date.today().isoformat()
        snapshots = {
            ticker: self.quant.research_snapshot(ticker, as_of=cutoff)
            for ticker in theme["tickers"]
        }
        official = self._official_context(tickers=theme["tickers"], as_of=cutoff)
        manifest = {
            "quant_root": str(self.quant.root),
            "read_only": True,
            "tickers": {
                ticker: {
                    "tradingview": {
                        "path": snapshot["tradingview"].get("path"),
                        "sha256": snapshot["tradingview"].get("sha256"),
                        "as_of": snapshot["tradingview"].get("as_of"),
                        "status": snapshot["tradingview"].get("status"),
                    },
                    "finviz": {
                        "path": snapshot["finviz"].get("path"),
                        "sha256": snapshot["finviz"].get("sha256"),
                        "fetched_at": snapshot["finviz"].get("fetched_at"),
                        "session_date": snapshot["finviz"].get("session_date"),
                        "status": snapshot["finviz"].get("status"),
                    },
                }
                for ticker, snapshot in snapshots.items()
            },
            "official_documents": {
                "filings": {
                    ticker: [
                        {
                            "id": row["id"], "sha256": row["sha256"], "as_of": row["as_of"],
                            "accession": (row.get("metadata") or {}).get("accession"),
                        }
                        for row in rows
                    ]
                    for ticker, rows in official["filings"].items()
                },
                "policies": [
                    {"id": row["id"], "sha256": row["sha256"], "as_of": row["as_of"]}
                    for row in official["policies"]
                ],
            },
        }
        run = self.store.create_research_run(
            slice_id=slice_id,
            universe_scope=theme["universe_scope"],
            as_of=cutoff,
            input_manifest=manifest,
            model_version=RESEARCH_MODEL_VERSION,
            prompt_version=METHOD_PROMPT_VERSION,
        )
        graph = self.store.create_graph(run_id=run["id"], slice_id=slice_id, as_of=cutoff)
        node_ids: dict[str, str] = {}
        for key, node_type, label, tickers in theme["nodes"]:
            entity = self.store.add_entity(
                kind=node_type,
                canonical_name=label,
                metadata={"tickers": tickers, "slice": slice_id},
            )
            node = self.store.add_graph_node(
                graph_id=graph["id"],
                entity_id=entity["id"],
                node_type=node_type,
                label=label,
                tag="FRAME",
                confidence="LOW",
                metadata={
                    "tickers": tickers,
                    "blueprint_only": True,
                    "requires_claim_review": True,
                },
            )
            node_ids[key] = node["id"]
        for source_key, target_key, edge_type in theme["edges"]:
            self.store.add_graph_edge(
                graph_id=graph["id"],
                source_node_id=node_ids[source_key],
                target_node_id=node_ids[target_key],
                edge_type=edge_type,
                state="proposed",
                tag="FRAME",
                confidence="LOW",
                observed_at=cutoff,
                metadata={"blueprint_only": True, "evidence_score": None},
            )
        graph_payload = self.store.get_graph(graph["id"])

        claims: list[dict] = []
        seen_claims: set[str] = set()
        for ticker in theme["tickers"]:
            for claim in self.store.list_claims(ticker=ticker, limit=500):
                if claim["id"] not in seen_claims:
                    claims.append(claim)
                    seen_claims.add(claim["id"])
        verified = [claim for claim in claims if claim["verification_state"] == "verified"]
        grade = self._evidence_grade(snapshots, verified)
        bottleneck = self.store.add_bottleneck_contract(
            run_id=run["id"],
            graph_id=graph["id"],
            title=theme["scarce_layer"],
            unit=str(theme["measurement_contract"].get("supply") or ""),
            expansion_lead_time="pending official measurement",
            qualification_lead_time="pending official measurement",
            easing_threshold={"status": "undefined", "reason": "requires reviewed source data"},
            observation_source_ids=[],
            resolution_date=(date.fromisoformat(cutoff[:10]) + timedelta(days=365)).isoformat(),
            status="candidate",
            dimensions={
                key: {"grade": "E", "status": "pending"}
                for key in ("capacity", "lead_time", "price", "qualification", "substitution")
            },
            evidence_claim_ids=[],
        )
        valuations = self._valuation_rows(
            run_id=run["id"], theme=theme, snapshots=snapshots, as_of=cutoff
        )
        profiles = self.store.list_method_profiles(source_id=SERENITY_SOURCE_ID)
        method = profiles[0] if profiles else self.method_profile(as_of=cutoff)["profile"]
        coverage = {
            "tickers": {
                ticker: snapshot["coverage"] for ticker, snapshot in snapshots.items()
            },
            "verified_claims": len(verified),
            "pending_claims": sum(claim["verification_state"] == "pending" for claim in claims),
            "official_filings": sum(len(rows) for rows in official["filings"].values()),
            "official_policy_documents": len(official["policies"]),
            "issues": [
                {"ticker": ticker, "issues": snapshot["issues"]}
                for ticker, snapshot in snapshots.items() if snapshot["issues"]
            ],
        }
        companies = [
            {
                "ticker": ticker,
                "value_chain_role": self._company_role(theme, ticker),
                "classification": "research_candidate",
                "constrains": theme["scarce_layer"],
                "value_capture": "unverified until operating evidence is reviewed",
                "substitutability": theme["measurement_contract"]["supply"],
                "capacity_lead_time": "pending official measurement",
                "qualification_lead_time": "pending official measurement",
                "demand_evidence": {
                    "tradingview": snapshots[ticker]["tradingview"],
                    "finviz": snapshots[ticker]["finviz"],
                },
                "financial_evidence": [
                    claim for claim in verified if claim.get("ticker") == ticker
                ],
                "official_filings": official["filings"][ticker],
                "relationship_hypotheses": [],
                "valuation_snapshots": valuations[ticker],
                "watch_metrics": theme["measurement_contract"]["watch"],
                "failure_conditions": theme["failure_conditions"],
            }
            for ticker in theme["tickers"]
        ]
        pack_payload = {
            "slice": slice_id,
            "title": theme["title"],
            "phase": theme["phase"],
            "universe_scope": theme["universe_scope"],
            "as_of": cutoff,
            "system_change": theme["system_change"],
            "constraint_type": theme["constraint_type"],
            "constraint_statement": theme["constraint_statement"],
            "scarce_layer": theme["scarce_layer"],
            "measurement_contract": theme["measurement_contract"],
            "graph_id": graph["id"],
            "graph": graph_payload,
            "tickers": theme["tickers"],
            "coverage": coverage,
            "evidence_grade": grade,
            "policy_exposure": theme["policy_exposure"],
            "policy_documents": official["policies"],
            "historical_analogues": theme["historical_analogues"],
            "next_move": theme["next_move"],
            "failure_conditions": theme["failure_conditions"],
            "companies": companies,
            "bottleneck_contract": bottleneck,
            "method_profile": method,
            "source_claims": claims,
            "llm_involvement": "none",
            "orders_generated": False,
            "content_contract": {
                "slice": slice_id,
                "as_of": cutoff,
                "model_version": RESEARCH_MODEL_VERSION,
                "prompt_version": METHOD_PROMPT_VERSION,
                "input_manifest": manifest,
                "verified_claim_ids": sorted(claim["id"] for claim in verified),
                "theme_blueprint": {
                    "nodes": theme["nodes"],
                    "edges": theme["edges"],
                    "measurement_contract": theme["measurement_contract"],
                },
            },
        }
        pack = None
        created = False
        if freeze:
            pack, created = self.store.freeze_research_pack(run_id=run["id"], payload=pack_payload)
        degraded = grade not in {"A", "B"} or bool(coverage["issues"])
        finished = self.store.finish_research_run(
            run["id"], status="degraded" if degraded else "complete"
        )
        return {
            "run": finished,
            "pack": pack,
            "pack_created": created,
            "payload": pack_payload,
            "orders_generated": False,
        }

    def packs(self, *, slice_id: str = "", limit: int = 100) -> list[dict]:
        return self.store.list_research_packs(slice_id=slice_id, limit=limit)

    def pack(self, pack_id: str) -> dict:
        row = self.store.get_research_pack(pack_id)
        if not row:
            raise LookupError(f"unknown research pack: {pack_id}")
        return row

    @staticmethod
    def _semantic_graph(graph: dict) -> tuple[set[tuple], set[tuple]]:
        nodes = graph.get("nodes") or []
        by_id = {row.get("id"): (row.get("node_type"), row.get("label")) for row in nodes}
        node_rows = {
            (row.get("node_type"), row.get("label"), row.get("tag"), row.get("confidence"))
            for row in nodes
        }
        edge_rows = {
            (
                by_id.get(row.get("source_node_id"), ("", ""))[1],
                by_id.get(row.get("target_node_id"), ("", ""))[1],
                row.get("edge_type"),
                row.get("state"),
                row.get("tag"),
            )
            for row in graph.get("edges") or []
        }
        return node_rows, edge_rows

    def pack_diff(self, pack_id: str, *, base_id: str = "") -> dict:
        current = self.pack(pack_id)
        if not base_id:
            base_id = str(current.get("previous_pack_id") or "")
        base = self.pack(base_id) if base_id else None
        if base is None:
            return {
                "pack_id": pack_id,
                "base_id": "",
                "initial": True,
                "changes": [{"kind": "pack_created", "slice": current["slice"]}],
            }
        current_payload = current.get("payload") or {}
        base_payload = base.get("payload") or {}
        changes: list[dict] = []
        for field in (
            "system_change", "constraint_statement", "scarce_layer", "evidence_grade",
            "next_move", "failure_conditions", "policy_exposure",
        ):
            if current_payload.get(field) != base_payload.get(field):
                changes.append(
                    {"kind": "field", "field": field,
                     "before": base_payload.get(field), "after": current_payload.get(field)}
                )
        current_nodes, current_edges = self._semantic_graph(current_payload.get("graph") or {})
        base_nodes, base_edges = self._semantic_graph(base_payload.get("graph") or {})
        for row in sorted(current_nodes - base_nodes):
            changes.append({"kind": "node_added", "value": row})
        for row in sorted(base_nodes - current_nodes):
            changes.append({"kind": "node_removed", "value": row})
        for row in sorted(current_edges - base_edges):
            changes.append({"kind": "edge_added_or_changed", "value": row})
        for row in sorted(base_edges - current_edges):
            changes.append({"kind": "edge_removed_or_changed", "value": row})

        def valuation_map(payload: dict) -> dict[tuple[str, str], tuple]:
            return {
                (company["ticker"], valuation["method"]):
                    (valuation.get("status"), valuation.get("low"),
                     valuation.get("mid"), valuation.get("high"))
                for company in payload.get("companies") or []
                for valuation in company.get("valuation_snapshots") or []
            }

        current_valuations = valuation_map(current_payload)
        base_valuations = valuation_map(base_payload)
        for key in sorted(set(current_valuations) | set(base_valuations)):
            if current_valuations.get(key) != base_valuations.get(key):
                changes.append(
                    {"kind": "valuation", "ticker": key[0], "method": key[1],
                     "before": base_valuations.get(key), "after": current_valuations.get(key)}
                )
        return {
            "pack_id": pack_id,
            "base_id": base_id,
            "initial": False,
            "same_content": current["content_hash"] == base["content_hash"],
            "changes": changes,
        }

    @staticmethod
    def _evidence_scores(edge: dict) -> dict:
        scores = {"support": 0, "refute": 0}
        dimensions = (
            "authority", "specificity", "temporal_consistency",
            "independence", "quant_consistency",
        )
        for evidence in edge.get("evidence") or []:
            stance = evidence.get("stance")
            if stance not in scores:
                continue
            detail = evidence.get("details") or {}
            score = sum(
                max(0, min(20, int(detail.get(dimension) or 0))) for dimension in dimensions
            )
            scores[stance] = min(100, scores[stance] + score)
        return {"support_score": scores["support"], "refute_score": scores["refute"]}

    def relationships(self, *, run_id: str = "", ticker: str = "") -> dict:
        graph_rows = self.store.list_graphs(run_id=run_id)
        edges: list[dict] = []
        for graph_row in graph_rows:
            graph = self.store.get_graph(graph_row["id"]) or {}
            nodes = {node["id"]: node for node in graph.get("nodes") or []}
            for edge in graph.get("edges") or []:
                if edge["edge_type"] != "commercial_relationship":
                    continue
                source = nodes.get(edge["source_node_id"], {})
                target = nodes.get(edge["target_node_id"], {})
                if ticker and ticker.upper() not in set(
                    (source.get("metadata") or {}).get("tickers", [])
                    + (target.get("metadata") or {}).get("tickers", [])
                ):
                    continue
                contract_id = edge.get("contract_id") or ""
                forecasts = self.store.list_forecasts(contract_id=contract_id) if contract_id else []
                latest = forecasts[0] if forecasts else {
                    "probability_status": "insufficient_data", "probability": None,
                    "lower_bound": None, "upper_bound": None,
                }
                edges.append(
                    {
                        **edge,
                        "source": source,
                        "target": target,
                        **self._evidence_scores(edge),
                        "p_relation": latest["probability"]
                            if latest["probability_status"] == "calibrated" else None,
                        "probability_status": latest["probability_status"],
                        "interval": [latest["lower_bound"], latest["upper_bound"]]
                            if latest["probability_status"] == "calibrated" else None,
                    }
                )
        contracts = [
            contract for contract in self.store.list_contracts(scope_id=ticker)
            if (contract.get("criteria") or {}).get("kind") == "official_named_relationship"
        ]
        return {"relationships": edges, "contracts": contracts}

    def create_relationship_contract(self, payload: dict) -> dict:
        criteria = dict(payload.get("criteria") or {})
        criteria["kind"] = "official_named_relationship"
        criteria.setdefault("requires_named_official_disclosure", True)
        criteria.setdefault("anonymous_concentration_is_insufficient", True)
        return self.store.add_contract(
            scope_type="ticker",
            scope_id=str(payload.get("ticker") or payload.get("scope_id") or ""),
            domain=str(payload.get("domain") or "commercial_relationship"),
            horizon=str(payload.get("horizon") or "1y"),
            statement=str(payload.get("statement") or ""),
            resolution_date=str(payload.get("resolution_date") or ""),
            criteria=criteria,
            resolution_source="manual_official",
            source_ids=[str(value) for value in payload.get("source_ids") or []],
            dependency_ids=[str(value) for value in payload.get("dependency_ids") or []],
        )

    def company(self, ticker: str) -> dict:
        symbol = ticker.upper().strip()
        packs = self.store.list_research_packs(limit=1000)
        cards = [
            company
            for pack in packs
            for company in (pack.get("payload") or {}).get("companies") or []
            if company.get("ticker") == symbol
        ]
        return {
            "ticker": symbol,
            "quant": self.quant.research_snapshot(symbol),
            "research_cards": cards,
            "official_filings": self._official_context(
                tickers=[symbol], as_of=date.today().isoformat()
            )["filings"][symbol],
            "relationships": self.relationships(ticker=symbol),
            "valuations": self.store.list_valuations(ticker=symbol),
            "orders_generated": False,
        }

    def coverage(self, *, run_id: str = "", source_id: str = "") -> dict:
        rows = self.store.list_source_coverage(run_id=run_id, source_id=source_id)
        totals = {
            key: sum(int(row.get(key) or 0) for row in rows)
            for key in ("retrieved", "deduplicated", "unavailable", "rate_limited", "index_only")
        }
        complete = bool(rows) and all(
            row.get("status") == "complete"
            and bool((row.get("details") or {}).get("archive_complete"))
            for row in rows
        )
        return {
            "rows": rows,
            "totals": totals,
            "complete": complete,
            "zero_means_unknown": True,
        }

    def live(self, *, limit: int = 100) -> dict:
        events: list[dict] = []
        for slice_id in THEMES:
            packs = self.store.list_research_packs(slice_id=slice_id, limit=2)
            if not packs:
                continue
            diff = self.pack_diff(
                packs[0]["id"], base_id=packs[1]["id"] if len(packs) > 1 else ""
            )
            for index, change in enumerate(diff["changes"]):
                events.append(
                    {
                        "id": f"{packs[0]['id']}:{index}",
                        "at": packs[0]["frozen_at"],
                        "slice": slice_id,
                        "pack_id": packs[0]["id"],
                        "kind": change["kind"],
                        "change": change,
                        "deterministic": True,
                    }
                )
        events.sort(key=lambda row: (row["at"], row["id"]), reverse=True)
        return {"events": events[: max(1, min(limit, 1000))]}

    def monitor(self) -> dict:
        runs = self.store.list_research_runs(limit=50)
        packs = self.store.list_research_packs(limit=50)
        return {
            "quant": self.quant.status(),
            "runs": runs,
            "packs": packs,
            "coverage": self.coverage(source_id=SERENITY_SOURCE_ID),
            "method_profiles": self.store.list_method_profiles(source_id=SERENITY_SOURCE_ID),
            "rules": {
                "llm_can_write_evidence": False,
                "llm_can_write_probability": False,
                "orders_generated": False,
                "same_manifest_same_hash": True,
            },
        }

    def stress_test(
        self,
        pack_id: str,
        question: str,
        *,
        critic: Optional[Callable[[dict, str], str]] = None,
    ) -> dict:
        pack = self.pack(pack_id)
        prompt = str(question or "").strip()[:600]
        if len(prompt) < 8:
            raise ValueError("ask a specific research question")
        payload = pack.get("payload") or {}
        before = pack["content_hash"]
        if critic is None:
            answer = {
                "strongest_counterargument": (payload.get("failure_conditions") or ["No failure condition defined."])[0],
                "missing_evidence": (payload.get("coverage") or {}).get("issues") or [
                    "No reviewed A/B evidence has been attached to the bottleneck contract."
                ],
                "next_research_move": payload.get("next_move") or "Define a measurable next step.",
            }
            involvement = "none"
        else:
            answer = {"critic_text": str(critic(payload, prompt))}
            involvement = "narration_only"
        after = self.pack(pack_id)["content_hash"]
        return {
            "pack_id": pack_id,
            "pack_hash": before,
            "question": prompt,
            "answer": answer,
            "llm_involvement": involvement,
            "mutated": before != after,
            "can_write_evidence": False,
            "can_write_probability": False,
            "orders_generated": False,
        }

    def daily_sync(self, *, as_of: str = "", serenity_days: int = 2) -> dict:
        serenity = self.serenity_backfill(days=serenity_days, count=500)
        research = [self.run_research(slice_id, as_of=as_of, freeze=True) for slice_id in THEMES]
        return {"serenity": serenity, "research": research, "orders_generated": False}

    def weekly_freeze(self, *, as_of: str = "") -> dict:
        return {
            "packs": [self.run_research(slice_id, as_of=as_of, freeze=True) for slice_id in THEMES],
            "orders_generated": False,
        }
