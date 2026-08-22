# -*- coding: utf-8
"""Multi-source A-share quote fetch with retry and coverage tracking."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from agent_reach.daily_run.retry_utils import retry_with_backoff


def normalize_code(code: str) -> str:
    text = str(code).strip()
    if text.isdigit():
        return text.zfill(6)[-6:]
    return text


def code_to_xueqiu_symbol(code: str) -> str:
    text = code.strip().upper()
    for prefix in ("SH", "SZ", "BJ"):
        if text.startswith(prefix):
            return text
    text = text.zfill(6)
    if text.startswith(("5", "6", "9")):
        return f"SH{text}"
    if text.startswith(("4", "8")):
        return f"BJ{text}"
    return f"SZ{text}"


def code_to_eastmoney_secid(code: str) -> str:
    """Eastmoney secid: 1.{sh/sz/bj code}."""
    text = normalize_code(code)
    if text.startswith(("5", "6", "9")):
        market = "1"
    elif text.startswith(("4", "8")):
        market = "0"
    else:
        market = "0"
    return f"{market}.{text}"


_EASTMONEY_FIELDS = "f43,f58,f60,f169,f170,f162,f168,f116"
_EASTMONEY_UA = "Mozilla/5.0 (compatible; AgentReach/1.0)"
_EASTMONEY_REFERER = "https://quote.eastmoney.com/"


def _parse_eastmoney_change_pct(data: dict[str, Any]) -> Optional[float]:
    """Parse daily change % from Eastmoney push2 stock/get (f170 is pct * 100)."""
    raw = data.get("f170")
    if raw is not None:
        return round(float(raw) / 100.0, 2)
    raw_price = data.get("f43")
    prev_close = data.get("f60")
    if raw_price is not None and prev_close:
        price = float(raw_price) / 100.0
        prev = float(prev_close) / 100.0
        if prev > 0:
            return round((price - prev) / prev * 100, 2)
    return None


def _optional_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if parsed <= 0 or parsed != parsed:
        return None
    return parsed


def _parse_eastmoney_pe_ttm(data: dict[str, Any]) -> Optional[float]:
    raw = _optional_float(data.get("f162"))
    if raw is None:
        return None
    if raw > 10000:
        return None
    if raw > 500:
        return round(raw / 100.0, 2)
    return round(raw, 2)


def _parse_eastmoney_turnover(data: dict[str, Any]) -> Optional[float]:
    from agent_reach.daily_run.valuation_metrics import normalize_turnover_pct

    raw = _optional_float(data.get("f168"))
    if raw is None:
        return None
    if raw > 100:
        raw = raw / 100.0
    return normalize_turnover_pct(raw)


def _parse_eastmoney_market_cap(data: dict[str, Any]) -> Optional[float]:
    from agent_reach.daily_run.valuation_metrics import normalize_market_cap_yuan

    return normalize_market_cap_yuan(data.get("f116"))


def _parse_eastmoney_valuation(data: dict[str, Any]) -> dict[str, float]:
    out: dict[str, float] = {}
    pe = _parse_eastmoney_pe_ttm(data)
    if pe is not None:
        out["pe_ttm"] = pe
    turnover = _parse_eastmoney_turnover(data)
    if turnover is not None:
        out["turnover_rate"] = turnover
    market_cap = _parse_eastmoney_market_cap(data)
    if market_cap is not None:
        out["market_capital"] = market_cap
    return out


def _fetch_eastmoney(codes: list[str], *, max_retries: int) -> dict[str, dict[str, Any]]:
    """Per-symbol Eastmoney push2 API — lighter than AKShare full spot table."""
    import json
    import ssl
    import urllib.request

    out: dict[str, dict[str, Any]] = {}
    ctx = ssl.create_default_context()

    def _fetch_one(code: str) -> Optional[dict[str, Any]]:
        secid = code_to_eastmoney_secid(code)
        url = (
            "https://push2.eastmoney.com/api/qt/stock/get"
            f"?secid={secid}&fields={_EASTMONEY_FIELDS}"
        )
        req = urllib.request.Request(
            url,
            headers={"User-Agent": _EASTMONEY_UA, "Referer": _EASTMONEY_REFERER},
        )
        with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        data = payload.get("data") or {}
        raw_price = data.get("f43")
        if raw_price is None:
            return None
        price = float(raw_price) / 100.0
        prev_raw = data.get("f60")
        prev_close = float(prev_raw) / 100.0 if prev_raw is not None else price
        row = {
            "code": normalize_code(code),
            "name": str(data.get("f58") or code),
            "price": price,
            "change_pct": _parse_eastmoney_change_pct(data),
            "reference_price": prev_close,
            "source": "eastmoney",
        }
        row.update(_parse_eastmoney_valuation(data))
        return row

    for code in codes:
        norm = normalize_code(code)
        try:
            row = retry_with_backoff(
                lambda c=code: _fetch_one(c),
                max_retries=max_retries,
                label=f"eastmoney_{norm}",
            )
        except Exception:
            continue
        if row and row.get("price"):
            out[norm] = row
    return out

_VALUATION_KEYS = ("pe_ttm", "turnover_rate", "market_capital")


def _merge_valuation_fields(base: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key in _VALUATION_KEYS:
        if out.get(key) is None and extra.get(key) is not None:
            out[key] = extra[key]
    return out


@dataclass
class QuoteFetchResult:
    quotes: dict[str, dict[str, Any]] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)
    sources_used: list[str] = field(default_factory=list)

    @property
    def coverage(self) -> float:
        return 0.0

    def coverage_for(self, codes: list[str]) -> float:
        if not codes:
            return 1.0
        unique = list(dict.fromkeys(normalize_code(c) for c in codes if c))
        if not unique:
            return 1.0
        hit = sum(1 for c in unique if c in self.quotes)
        return hit / len(unique)


def _fetch_xueqiu(codes: list[str], *, max_retries: int) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}

    def _load_channel():
        from agent_reach.channels import xueqiu as xq_mod

        xq_mod._ensure_cookies()
        return xq_mod.XueqiuChannel()

    channel = retry_with_backoff(_load_channel, max_retries=max_retries, label="xueqiu_channel")
    for code in codes:
        try:
            q = retry_with_backoff(
                lambda c=code: channel.get_stock_quote(code_to_xueqiu_symbol(c)),
                max_retries=max_retries,
                label=f"xueqiu_{code}",
            )
            price = q.get("current")
            if price is None:
                continue
            out[code] = {
                "code": code,
                "name": q.get("name", code),
                "price": float(price),
                "change_pct": float(q.get("percent") or 0),
                "reference_price": float(q.get("last_close") or price),
                "source": "xueqiu",
            }
            pe = q.get("pe_ttm")
            if pe is not None:
                try:
                    out[code]["pe_ttm"] = float(pe)
                except (TypeError, ValueError):
                    pass
            turnover = q.get("turnover_rate")
            if turnover is not None:
                try:
                    out[code]["turnover_rate"] = float(turnover)
                except (TypeError, ValueError):
                    pass
            market_cap = q.get("market_capital")
            if market_cap is not None:
                try:
                    out[code]["market_capital"] = float(market_cap)
                except (TypeError, ValueError):
                    pass
        except Exception:
            continue
    return out


def _fetch_akshare(codes: list[str], *, max_retries: int, ttl: int) -> dict[str, dict[str, Any]]:
    from agent_reach.daily_run.akshare_adapter import fetch_quotes_batch

    return retry_with_backoff(
        lambda: fetch_quotes_batch(codes, ttl=ttl),
        max_retries=max_retries,
        label="akshare_batch",
    )


def fetch_quotes_map(
    codes: list[str],
    config=None,
    *,
    settings: Optional[dict[str, Any]] = None,
) -> QuoteFetchResult:
    """Fetch quotes using configured source priority with retry."""
    from agent_reach.daily_run.settings import load_settings

    cfg = settings or load_settings()
    qcfg = cfg.get("quote_fetch") or {}
    order = qcfg.get("sources") or ["eastmoney", "xueqiu", "akshare"]
    max_retries = int(qcfg.get("max_retries", 2))
    ttl = int((cfg.get("akshare") or {}).get("spot_ttl", 60))

    unique = list(dict.fromkeys(normalize_code(c) for c in codes if c))
    result = QuoteFetchResult()
    missing = list(unique)

    fetchers = {
        "eastmoney": lambda cs: _fetch_eastmoney(cs, max_retries=max_retries),
        "xueqiu": lambda cs: _fetch_xueqiu(cs, max_retries=max_retries),
        "akshare": lambda cs: _fetch_akshare(cs, max_retries=max_retries, ttl=ttl),
    }

    for source in order:
        if not missing:
            break
        fn = fetchers.get(source)
        if fn is None:
            continue
        try:
            batch = fn(missing)
        except Exception as exc:
            for code in missing:
                result.errors.setdefault(code, f"{source}: {exc}")
            continue
        if batch:
            result.sources_used.append(source)
        for code in list(missing):
            if code in batch:
                result.quotes[code] = batch[code]
                missing.remove(code)
                result.errors.pop(code, None)
        for code, row in batch.items():
            if code in result.quotes:
                result.quotes[code] = _merge_valuation_fields(result.quotes[code], row)

    for code in missing:
        result.errors.setdefault(code, "no quote from configured sources")
    return result
