# -*- coding: utf-8
"""Agent Reach context store: cases, harness sidecars, agentreach:// URI resolution."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Literal, Optional

from agent_reach.daily_run.context_layers import (
    agentreach_uri,
    layer0,
    layer1,
    write_text_sidecars,
)

LayerName = Literal["abstract", "overview", "detail", "l0", "l1", "l2"]

_AGENTREACH_ROOT = Path.home() / ".agent-reach"
_DAILY_RUN_ROOT = _AGENTREACH_ROOT / "daily_run"


def daily_run_root() -> Path:
    return _DAILY_RUN_ROOT


def cases_root() -> Path:
    return _DAILY_RUN_ROOT / "memory" / "cases"


def harness_entries_root() -> Path:
    return _DAILY_RUN_ROOT / "harness" / "entries"


def skill_root() -> Path:
    return _DAILY_RUN_ROOT / "skill"


def _normalize_layer(layer: str) -> LayerName:
    key = str(layer or "abstract").strip().lower()
    if key in ("l0", "abstract", "abs"):
        return "abstract"
    if key in ("l1", "overview", "ov"):
        return "overview"
    return "detail"


def _slug_part(text: str, *, limit: int = 32) -> str:
    raw = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", "-", str(text or "").strip()).strip("-")
    if not raw:
        raw = "case"
    return raw[:limit]


def trade_case_id(trade_record: dict[str, Any]) -> str:
    from agent_reach.daily_run.snapshot_builder import _normalize_code

    code = _normalize_code(str(trade_record.get("code") or "UNK"))
    trade_id = str(trade_record.get("trade_id") or "T")
    msg = str(trade_record.get("portfolio_message") or trade_record.get("reasoning") or "")
    if "最小单位" in msg or "一手" in msg or "资金不足" in msg:
        reason = "cash-lot-fail"
    elif trade_record.get("cash_limit_bypass"):
        reason = "cash-bypass"
    elif trade_record.get("blocked"):
        reason = str(trade_record.get("block_kind") or "blocked")
    elif not trade_record.get("portfolio_applied", True):
        reason = "not-applied"
    else:
        reason = str(trade_record.get("action") or "trade")
    return f"{code}-{trade_id}-{_slug_part(reason)}"


def should_record_trade_case(trade_record: dict[str, Any]) -> bool:
    action = str(trade_record.get("action") or "").strip().lower()
    if action not in ("buy", "sell"):
        return False
    if trade_record.get("portfolio_applied"):
        return False
    return bool(
        trade_record.get("portfolio_message")
        or trade_record.get("blocked")
        or trade_record.get("cash_limit_bypass")
    )


def _build_case_overview(
    trade_record: dict[str, Any],
    *,
    portfolio_snapshot: Optional[dict[str, Any]] = None,
    price: Optional[float] = None,
    settings: Optional[dict[str, Any]] = None,
) -> str:
    lines = [
        f"# {trade_record.get('name') or trade_record.get('code')} · {trade_record.get('trade_id')}",
        "",
        f"- **动作：** {trade_record.get('action')}",
        f"- **Lookback MSS：** {trade_record.get('lookback_mss')}",
        f"- **趋势：** {trade_record.get('trend')}",
        f"- **落账：** {'是' if trade_record.get('portfolio_applied') else '否'}",
    ]
    if trade_record.get("portfolio_message"):
        lines.append(f"- **落账说明：** {trade_record['portfolio_message']}")
    if trade_record.get("cash_limit_bypass"):
        streak = trade_record.get("consecutive_buy_streak")
        lines.append(f"- **连续买入突破：** 是（{streak or '?'} 次）")
    pf = portfolio_snapshot or {}
    if pf.get("cash") is not None:
        lines.append(f"- **现金：** ¥{float(pf['cash']):,.0f}")
    if pf.get("total") is not None:
        lines.append(f"- **总资产：** ¥{float(pf['total']):,.0f}")
    if pf.get("cash_ratio") is not None:
        lines.append(f"- **现金占比：** {float(pf['cash_ratio']):.1%}")
    if price is not None:
        lines.append(f"- **报价：** ¥{float(price):.2f}")
    runtime = (settings or {}).get("harness_runtime") or {}
    pos = runtime.get("position_overlay") or {}
    deploy = pos.get("deploy_ratio")
    if isinstance(deploy, dict):
        lines.append(
            f"- **deploy_ratio：** {float(deploy.get('base', 0)):.0%}"
            f"→{float(deploy.get('effective', 0)):.0%}"
        )
    thresh = runtime.get("threshold_overlay") or {}
    min_cash = thresh.get("min_cash_ratio")
    if isinstance(min_cash, dict):
        lines.append(
            f"- **min_cash_ratio：** {float(min_cash.get('base', 0)):.0%}"
            f"→{float(min_cash.get('effective', 0)):.0%}"
        )
    if trade_record.get("reasoning"):
        lines.append("")
        lines.append(f"**决策：** {trade_record['reasoning']}")
    return "\n".join(lines)


def _build_case_abstract(trade_record: dict[str, Any]) -> str:
    name = trade_record.get("name") or trade_record.get("code") or "?"
    action = trade_record.get("action") or "?"
    trade_id = trade_record.get("trade_id") or "?"
    msg = trade_record.get("portfolio_message") or trade_record.get("reasoning") or ""
    status = "已落账" if trade_record.get("portfolio_applied") else "未落账"
    return layer0(f"{name} {trade_id} {action} {status}：{msg}")


def record_trade_case(
    trade_record: dict[str, Any],
    *,
    portfolio_snapshot: Optional[dict[str, Any]] = None,
    price: Optional[float] = None,
    settings: Optional[dict[str, Any]] = None,
) -> Optional[str]:
    """Persist a failed/blocked intraday trade as structured case memory."""
    if not should_record_trade_case(trade_record):
        return None
    case_id = trade_case_id(trade_record)
    case_dir = cases_root() / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    uri = agentreach_uri("daily_run", "memory", "cases", case_id)
    overview = _build_case_overview(
        trade_record,
        portfolio_snapshot=portfolio_snapshot,
        price=price,
        settings=settings,
    )
    abstract = _build_case_abstract(trade_record)
    detail_path = case_dir / "detail.json"
    detail_path.write_text(
        json.dumps(trade_record, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (case_dir / ".abstract.md").write_text(abstract + "\n", encoding="utf-8")
    (case_dir / ".overview.md").write_text(layer1(overview) + "\n", encoding="utf-8")
    meta = {
        "case_id": case_id,
        "uri": uri,
        "code": trade_record.get("code"),
        "name": trade_record.get("name"),
        "trade_id": trade_record.get("trade_id"),
        "action": trade_record.get("action"),
        "portfolio_applied": trade_record.get("portfolio_applied"),
        "portfolio_message": trade_record.get("portfolio_message"),
        "updated_at": trade_record.get("as_of"),
    }
    (case_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return uri


def sync_harness_sidecars(state: Any) -> int:
    """Write harness entry markdown + L0/L1 sidecars under harness/entries/."""
    root = harness_entries_root()
    count = 0
    entries = getattr(state, "entries", {}) or {}
    for kind, bucket in entries.items():
        if not isinstance(bucket, dict):
            continue
        kind_dir = root / str(kind)
        kind_dir.mkdir(parents=True, exist_ok=True)
        for entry_id, entry in bucket.items():
            title = getattr(entry, "title", None) or (entry.get("title") if isinstance(entry, dict) else entry_id)
            content = getattr(entry, "content", None) or (entry.get("content") if isinstance(entry, dict) else "")
            body = f"# {title}\n\n{content}\n".strip() + "\n"
            path = kind_dir / f"{entry_id}.md"
            path.write_text(body, encoding="utf-8")
            write_text_sidecars(path, body)
            count += 1
    return count


def parse_agentreach_uri(uri: str) -> tuple[str, list[str]]:
    raw = str(uri or "").strip()
    if raw.startswith("agentreach://"):
        raw = raw[len("agentreach://") :]
    elif raw.startswith("~/"):
        return "filesystem", [str(Path(raw).expanduser())]
    parts = [p for p in raw.split("/") if p]
    if not parts:
        return "daily_run", []
    if parts[0] != "daily_run":
        parts = ["daily_run", *parts]
    return parts[0], parts[1:]


def resolve_uri(uri: str) -> Path:
    """Resolve agentreach:// URI or filesystem path."""
    _root, parts = parse_agentreach_uri(uri)
    if _root == "filesystem":
        return Path(parts[0])
    if not parts:
        return daily_run_root()
    if parts[0] == "memory" and parts[1] == "cases":
        if len(parts) == 2:
            return cases_root()
        return cases_root() / parts[2]
    if parts[0] == "harness" and len(parts) >= 4 and parts[1] == "entries":
        kind, entry_id = parts[2], parts[3]
        return harness_entries_root() / kind / f"{entry_id}.md"
    if parts[0] == "skill":
        return skill_root() / "/".join(parts[1:])
    return daily_run_root().joinpath(*parts)


def _layer_path(target: Path, layer: LayerName) -> Path:
    layer = _normalize_layer(layer)
    if target.is_dir():
        if layer == "abstract":
            return target / ".abstract.md"
        if layer == "overview":
            return target / ".overview.md"
        return target / "detail.json"
    stem = target.stem
    parent = target.parent
    if layer == "abstract":
        sidecar = parent / f"{stem}.abstract.md"
        if sidecar.exists():
            return sidecar
        return parent / ".abstract.md"
    if layer == "overview":
        sidecar = parent / f"{stem}.overview.md"
        if sidecar.exists():
            return sidecar
        return parent / ".overview.md"
    return target


def read_layer(uri: str, *, layer: str = "abstract") -> str:
    target = resolve_uri(uri)
    if not target.exists() and not target.is_dir():
        raise FileNotFoundError(f"not found: {uri}")
    path = _layer_path(target, _normalize_layer(layer))
    if not path.exists():
        if target.is_file():
            return target.read_text(encoding="utf-8")
        raise FileNotFoundError(f"layer not found: {path}")
    return path.read_text(encoding="utf-8")


def list_context(uri: str = "agentreach://daily_run", *, layer: str = "abstract") -> list[dict[str, Any]]:
    target = resolve_uri(uri)
    if not target.exists():
        return []
    rows: list[dict[str, Any]] = []
    if target.is_file():
        rows.append(
            {
                "uri": uri,
                "path": str(target),
                "abstract": layer0(read_layer(uri, layer="abstract")) if target.exists() else "",
            }
        )
        return rows
    for child in sorted(target.iterdir()):
        if child.name.startswith("."):
            continue
        if child.is_dir():
            if not ((child / "meta.json").exists() or (child / "detail.json").exists()):
                continue
            case_uri = agentreach_uri("daily_run", "memory", "cases", child.name)
            abstract = ""
            abs_path = child / ".abstract.md"
            if abs_path.exists():
                abstract = layer0(abs_path.read_text(encoding="utf-8"))
            rows.append({"uri": case_uri, "path": str(child), "abstract": abstract, "kind": "case"})
            continue
        if child.suffix == ".md" and not child.name.endswith(".abstract.md") and not child.name.endswith(".overview.md"):
            rel_uri = uri.rstrip("/") + "/" + child.name if uri.startswith("agentreach://") else str(child)
            abs_file = child.with_name(f"{child.stem}.abstract.md")
            abstract = layer0(abs_file.read_text(encoding="utf-8")) if abs_file.exists() else layer0(child.stem)
            rows.append({"uri": rel_uri, "path": str(child), "abstract": abstract})
    return rows


def find_context(
    query: str,
    *,
    kind: str = "",
    code: str = "",
    limit: int = 8,
) -> list[dict[str, Any]]:
    """Simple substring search across case abstracts and harness sidecars."""
    q = str(query or "").strip().lower()
    code_norm = str(code or "").strip()
    hits: list[tuple[int, dict[str, Any]]] = []

    def _score(text: str) -> int:
        blob = text.lower()
        if not q:
            return 1
        score = 0
        if q in blob:
            score += 10
        for token in q.split():
            if token and token in blob:
                score += 3
        return score

    if kind in ("", "cases", "case"):
        root = cases_root()
        if root.exists():
            for case_dir in root.iterdir():
                if not case_dir.is_dir():
                    continue
                if not ((case_dir / "meta.json").exists() or (case_dir / "detail.json").exists()):
                    continue
                meta_path = case_dir / "meta.json"
                meta: dict[str, Any] = {}
                if meta_path.exists():
                    try:
                        meta = json.loads(meta_path.read_text(encoding="utf-8"))
                    except json.JSONDecodeError:
                        meta = {}
                if code_norm and str(meta.get("code") or case_dir.name).find(code_norm) < 0:
                    continue
                abs_path = case_dir / ".abstract.md"
                abstract = abs_path.read_text(encoding="utf-8") if abs_path.exists() else case_dir.name
                score = _score(abstract + " " + json.dumps(meta, ensure_ascii=False))
                if score <= 0 and q:
                    continue
                hits.append(
                    (
                        score,
                        {
                            "uri": agentreach_uri("daily_run", "memory", "cases", case_dir.name),
                            "kind": "case",
                            "abstract": layer0(abstract),
                            "code": meta.get("code"),
                            "trade_id": meta.get("trade_id"),
                        },
                    )
                )

    if kind in ("", "harness"):
        root = harness_entries_root()
        if root.exists():
            for kind_dir in root.iterdir():
                if not kind_dir.is_dir():
                    continue
                for md in kind_dir.glob("*.md"):
                    if md.name.endswith(".abstract.md") or md.name.endswith(".overview.md"):
                        continue
                    abs_file = md.with_name(f"{md.stem}.abstract.md")
                    abstract = abs_file.read_text(encoding="utf-8") if abs_file.exists() else md.stem
                    score = _score(abstract)
                    if score <= 0 and q:
                        continue
                    hits.append(
                        (
                            score,
                            {
                                "uri": agentreach_uri(
                                    "daily_run", "harness", "entries", kind_dir.name, md.stem
                                ),
                                "kind": f"harness/{kind_dir.name}",
                                "abstract": layer0(abstract),
                            },
                        )
                    )

    if kind in ("", "skill"):
        root = skill_root()
        if root.exists():
            for md in root.glob("*.md"):
                if md.name.endswith(".abstract.md") or md.name.endswith(".overview.md"):
                    continue
                abs_file = md.with_name(f"{md.stem}.abstract.md")
                abstract = abs_file.read_text(encoding="utf-8") if abs_file.exists() else md.stem
                score = _score(abstract)
                if score <= 0 and q:
                    continue
                hits.append(
                    (
                        score,
                        {
                            "uri": agentreach_uri("daily_run", "skill", md.name),
                            "kind": "skill",
                            "abstract": layer0(abstract),
                        },
                    )
                )

    hits.sort(key=lambda item: item[0], reverse=True)
    return [row for _, row in hits[:limit]]


def find_cases_for_symbol(code: str, *, limit: int = 2) -> list[str]:
    rows = find_context("", kind="cases", code=code, limit=limit)
    return [str(row.get("abstract") or "") for row in rows if row.get("abstract")]
