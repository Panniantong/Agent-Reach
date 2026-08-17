# -*- coding: utf-8
"""Persist daily portfolio P&L and render trend charts."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Optional

from agent_reach.daily_run.trade_calendar import today_shanghai


@dataclass
class DailyPnlRecord:
    date: str
    daily_pnl: float
    daily_pnl_pct: Optional[float] = None
    start_total: Optional[float] = None
    end_total: Optional[float] = None
    realized_pnl: Optional[float] = None
    capital_net_flow: Optional[float] = None
    cumulative_pnl: Optional[float] = None
    source: str = "close"
    manifest_path: str = ""
    recorded_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "date": self.date,
            "daily_pnl": round(float(self.daily_pnl), 2),
            "daily_pnl_pct": self.daily_pnl_pct,
            "start_total": self.start_total,
            "end_total": self.end_total,
            "realized_pnl": self.realized_pnl,
            "capital_net_flow": self.capital_net_flow,
            "cumulative_pnl": self.cumulative_pnl,
            "source": self.source,
            "manifest_path": self.manifest_path,
            "recorded_at": self.recorded_at,
        }

    @classmethod
    def from_dict(cls, row: dict[str, Any]) -> DailyPnlRecord:
        return cls(
            date=str(row.get("date") or ""),
            daily_pnl=float(row.get("daily_pnl") or 0),
            daily_pnl_pct=(
                float(row["daily_pnl_pct"]) if row.get("daily_pnl_pct") is not None else None
            ),
            start_total=(
                float(row["start_total"]) if row.get("start_total") is not None else None
            ),
            end_total=float(row["end_total"]) if row.get("end_total") is not None else None,
            realized_pnl=(
                float(row["realized_pnl"]) if row.get("realized_pnl") is not None else None
            ),
            capital_net_flow=(
                float(row["capital_net_flow"])
                if row.get("capital_net_flow") is not None
                else None
            ),
            cumulative_pnl=(
                float(row["cumulative_pnl"])
                if row.get("cumulative_pnl") is not None
                else None
            ),
            source=str(row.get("source") or "close"),
            manifest_path=str(row.get("manifest_path") or ""),
            recorded_at=str(row.get("recorded_at") or ""),
        )


def default_pnl_history_path() -> Path:
    return Path.home() / ".agent-reach" / "daily_run" / "pnl_history.jsonl"


def summary_to_history_row(
    summary: dict[str, Any],
    *,
    source: str = "close",
    manifest_path: str = "",
    recorded_at: str = "",
) -> Optional[DailyPnlRecord]:
    day = str(summary.get("as_of") or "")[:10]
    daily_pnl = summary.get("daily_pnl")
    if not day or daily_pnl is None:
        return None
    return DailyPnlRecord(
        date=day,
        daily_pnl=float(daily_pnl),
        daily_pnl_pct=(
            float(summary["daily_pnl_pct"]) if summary.get("daily_pnl_pct") is not None else None
        ),
        start_total=(
            float(summary["start_total"]) if summary.get("start_total") is not None else None
        ),
        end_total=float(summary["end_total"]) if summary.get("end_total") is not None else None,
        realized_pnl=(
            float(summary["realized_pnl"]) if summary.get("realized_pnl") is not None else None
        ),
        capital_net_flow=(
            float(summary["capital_net_flow"])
            if summary.get("capital_net_flow") is not None
            else None
        ),
        source=source,
        manifest_path=manifest_path,
        recorded_at=recorded_at,
    )


def load_daily_pnl_history(
    *,
    path: Optional[Path] = None,
    start: Optional[date] = None,
    end: Optional[date] = None,
) -> list[DailyPnlRecord]:
    p = path or default_pnl_history_path()
    if not p.is_file():
        return []
    by_date: dict[str, DailyPnlRecord] = {}
    with open(p, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            rec = DailyPnlRecord.from_dict(row)
            if not rec.date:
                continue
            if start is not None and rec.date < start.isoformat():
                continue
            if end is not None and rec.date > end.isoformat():
                continue
            by_date[rec.date] = rec
    return [by_date[d] for d in sorted(by_date)]


def _write_history_rows(rows: list[DailyPnlRecord], *, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(r.to_dict(), ensure_ascii=False) for r in rows]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def append_daily_pnl(
    summary: dict[str, Any],
    *,
    source: str = "close",
    manifest_path: str = "",
    path: Optional[Path] = None,
) -> Optional[DailyPnlRecord]:
    """Upsert one daily P&L row (one record per trading date)."""
    from datetime import datetime, timezone

    row = summary_to_history_row(
        summary,
        source=source,
        manifest_path=manifest_path,
        recorded_at=datetime.now(timezone.utc).isoformat(),
    )
    if row is None:
        return None

    p = path or default_pnl_history_path()
    existing = load_daily_pnl_history(path=p)
    by_date = {r.date: r for r in existing}
    by_date[row.date] = row
    merged = [by_date[d] for d in sorted(by_date)]
    attach_cumulative_pnl(merged)
    _write_history_rows(merged, path=p)
    return by_date[row.date]


def attach_cumulative_pnl(rows: list[DailyPnlRecord]) -> list[DailyPnlRecord]:
    total = 0.0
    for row in rows:
        total = round(total + float(row.daily_pnl), 2)
        row.cumulative_pnl = total
    return rows


def backfill_from_manifests(
    *,
    start: Optional[date] = None,
    end: Optional[date] = None,
    path: Optional[Path] = None,
) -> dict[str, Any]:
    """Import daily P&L from close run manifests (latest close per day)."""
    from agent_reach.daily_run.weekly_report import (
        _iter_manifest_files,
        _load_manifest,
        _portfolio_summary_from_manifest,
    )

    end_day = end or today_shanghai()
    start_day = start or (end_day - timedelta(days=365))
    imported: dict[str, DailyPnlRecord] = {}

    for day, mpath in _iter_manifest_files(start_day, end_day):
        record = _load_manifest(mpath)
        if not record or record.get("job") != "close":
            continue
        ps = _portfolio_summary_from_manifest(record)
        if not ps:
            continue
        row = summary_to_history_row(ps, source="manifest", manifest_path=str(mpath))
        if row is None:
            continue
        day_str = row.date
        imported[day_str] = row

    p = path or default_pnl_history_path()
    existing = {r.date: r for r in load_daily_pnl_history(path=p)}
    for day_str, row in imported.items():
        if day_str not in existing or existing[day_str].source == "manifest":
            existing[day_str] = row
    merged = [existing[d] for d in sorted(existing)]
    attach_cumulative_pnl(merged)
    _write_history_rows(merged, path=p)
    return {
        "ok": True,
        "imported": len(imported),
        "total_rows": len(merged),
        "path": str(p),
    }


def render_pnl_line_chart_ascii(
    rows: list[DailyPnlRecord | dict[str, Any]],
    *,
    value_key: str = "daily_pnl",
    width: int = 56,
    height: int = 10,
    title: str = "",
) -> str:
    """Render a simple ASCII line chart (supports negative values)."""
    if not rows:
        return "(no data)"

    points: list[tuple[str, float]] = []
    for row in rows:
        data = row.to_dict() if isinstance(row, DailyPnlRecord) else row
        day = str(data.get("date") or "")[-5:]
        val = data.get(value_key)
        if val is None:
            continue
        points.append((day, float(val)))
    if not points:
        return "(no numeric data)"

    if len(points) > width:
        step = len(points) / width
        sampled: list[tuple[str, float]] = []
        for i in range(width):
            idx = min(int(i * step), len(points) - 1)
            sampled.append(points[idx])
        points = sampled

    values = [v for _, v in points]
    lo = min(min(values), 0.0)
    hi = max(max(values), 0.0)
    if hi == lo:
        hi = lo + 1.0

    grid: list[list[str]] = [[" " for _ in range(len(points))] for _ in range(height)]

    def y_to_row(y: float) -> int:
        ratio = (y - lo) / (hi - lo)
        return height - 1 - int(round(ratio * (height - 1)))

    zero_row = y_to_row(0.0) if lo < 0 < hi else None
    if zero_row is not None:
        for x in range(len(points)):
            grid[zero_row][x] = "─"

    prev_row: Optional[int] = None
    for x, (_, val) in enumerate(points):
        row_idx = y_to_row(val)
        grid[row_idx][x] = "●"
        if prev_row is not None and x > 0:
            r0, r1 = prev_row, row_idx
            step_dir = 1 if r1 >= r0 else -1
            for r in range(r0 + step_dir, r1, step_dir):
                if grid[r][x - 1] == " ":
                    grid[r][x - 1] = "│"
                if grid[r][x] == " ":
                    grid[r][x] = "│"
        prev_row = row_idx

    lines: list[str] = []
    if title:
        lines.append(title)
    for r in range(height):
        y_val = hi - (hi - lo) * r / max(height - 1, 1)
        label = f"{y_val:+8,.0f} │"
        lines.append(label + "".join(grid[r]))
    if len(points) <= 20:
        labels = " " * 10 + " ".join(f"{lbl:>4}" for lbl, _ in points)
    else:
        labels = " " * 10 + f"{points[0][0]} … {points[-1][0]}"
    lines.append(labels)
    return "\n".join(lines)


def render_pnl_line_chart_svg(
    rows: list[DailyPnlRecord | dict[str, Any]],
    *,
    value_key: str = "cumulative_pnl",
    width: int = 720,
    height: int = 220,
    title: str = "累计盈亏",
) -> str:
    if not rows:
        return '<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1"></svg>'

    points: list[tuple[str, float]] = []
    for row in rows:
        data = row.to_dict() if isinstance(row, DailyPnlRecord) else row
        day = str(data.get("date") or "")
        val = data.get(value_key)
        if val is None:
            continue
        points.append((day, float(val)))
    if not points:
        return '<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1"></svg>'

    pad_l, pad_r, pad_t, pad_b = 56, 16, 28, 36
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b
    values = [v for _, v in points]
    lo = min(min(values), 0.0)
    hi = max(max(values), 0.0)
    if hi == lo:
        hi = lo + 1.0

    def x_pos(i: int) -> float:
        if len(points) == 1:
            return pad_l + plot_w / 2
        return pad_l + plot_w * i / (len(points) - 1)

    def y_pos(v: float) -> float:
        return pad_t + plot_h * (1 - (v - lo) / (hi - lo))

    coords = " ".join(f"{x_pos(i):.1f},{y_pos(v):.1f}" for i, (_, v) in enumerate(points))
    zero_y = y_pos(0.0) if lo < 0 < hi else None

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">',
        f'<rect width="{width}" height="{height}" fill="#fafafa"/>',
        f'<text x="{pad_l}" y="18" font-size="14" fill="#333">{title}</text>',
        f'<rect x="{pad_l}" y="{pad_t}" width="{plot_w}" height="{plot_h}" '
        f'fill="#fff" stroke="#ddd"/>',
    ]
    if zero_y is not None:
        parts.append(
            f'<line x1="{pad_l}" y1="{zero_y:.1f}" x2="{pad_l + plot_w}" y2="{zero_y:.1f}" '
            f'stroke="#ccc" stroke-dasharray="4 3"/>'
        )
    parts.append(
        f'<polyline fill="none" stroke="#2563eb" stroke-width="2" points="{coords}"/>'
    )
    for i, (_, v) in enumerate(points):
        cx, cy = x_pos(i), y_pos(v)
        color = "#16a34a" if v >= 0 else "#dc2626"
        parts.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="3" fill="{color}"/>')
    if points:
        parts.append(
            f'<text x="{pad_l}" y="{height - 8}" font-size="11" fill="#666">'
            f'{points[0][0]}</text>'
        )
        parts.append(
            f'<text x="{pad_l + plot_w}" y="{height - 8}" font-size="11" fill="#666" '
            f'text-anchor="end">{points[-1][0]}</text>'
        )
    parts.append(
        f'<text x="8" y="{pad_t + 4}" font-size="11" fill="#666">{hi:+,.0f}</text>'
    )
    parts.append(
        f'<text x="8" y="{pad_t + plot_h}" font-size="11" fill="#666">{lo:+,.0f}</text>'
    )
    parts.append("</svg>")
    return "\n".join(parts)


def render_pnl_history_markdown(
    rows: list[DailyPnlRecord],
    *,
    days: int = 30,
) -> str:
    if not rows:
        return "## 📈 每日盈亏\n\n暂无历史记录。收盘后自动写入，或运行 `daily-run pnl history --backfill`。"

    recent = rows[-days:] if days > 0 else rows
    lines = ["## 📈 每日盈亏", ""]
    lines.append("| 日期 | 当日盈亏 | 累计 | 净值 |")
    lines.append("|------|---------:|-----:|-----:|")
    for row in recent:
        pct = f" ({row.daily_pnl_pct:+.2f}%)" if row.daily_pnl_pct is not None else ""
        end_total = f"{row.end_total:,.0f}" if row.end_total is not None else "—"
        cum = f"{row.cumulative_pnl:+,.0f}" if row.cumulative_pnl is not None else "—"
        lines.append(
            f"| {row.date} | {row.daily_pnl:+,.0f}{pct} | {cum} | {end_total} |"
        )
    return "\n".join(lines)
