"""Read-only audit of the canonical GBPUSD M5 data contract."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from gbpusd_structure.config import ResearchConfig

REQUIRED_M5_COLUMNS = {
    "timestamp",
    "bid_open",
    "bid_high",
    "bid_low",
    "bid_close",
    "ask_open",
    "ask_high",
    "ask_low",
    "ask_close",
    "mid_open",
    "mid_high",
    "mid_low",
    "mid_close",
    "tick_count",
    "activity_count",
    "spread_open_pips",
    "spread_median_pips",
    "spread_p95_pips",
    "spread_max_pips",
    "first_tick_timestamp",
    "last_tick_timestamp",
}


def iter_months(start: date, end: date) -> tuple[str, ...]:
    if end <= start:
        raise ValueError("end must be later than start")
    output = []
    current = date(start.year, start.month, 1)
    while current < end:
        output.append(f"{current.year:04d}-{current.month:02d}")
        current = (
            date(current.year + 1, 1, 1)
            if current.month == 12
            else date(current.year, current.month + 1, 1)
        )
    return tuple(output)


def audit_canonical_m5(data_root: Path, research: ResearchConfig) -> dict[str, Any]:
    """Validate coverage/schema and summarize observed Bid/Ask spreads."""

    expected_months = iter_months(
        research.periods.research_start, research.periods.research_end
    )
    discovered = sorted(data_root.glob(research.data.canonical_m5_glob))
    by_month = {
        path.stem.removeprefix("m5-"): path
        for path in discovered
        if path.stem.startswith("m5-")
    }
    missing_months = sorted(set(expected_months).difference(by_month))
    selected = [by_month[month] for month in expected_months if month in by_month]

    frames = []
    schema_errors: dict[str, list[str]] = {}
    for path in selected:
        frame = pd.read_parquet(path)
        missing_columns = sorted(REQUIRED_M5_COLUMNS.difference(frame.columns))
        if missing_columns:
            schema_errors[str(path.relative_to(data_root))] = missing_columns
            continue
        frames.append(frame[list(sorted(REQUIRED_M5_COLUMNS))])

    if not frames:
        return {
            "valid": False,
            "data_root": str(data_root),
            "price_source": research.data.price_source,
            "expected_months": list(expected_months),
            "available_months": sorted(set(expected_months).intersection(by_month)),
            "missing_months": missing_months,
            "schema_errors": schema_errors,
            "bar_count": 0,
        }

    bars = pd.concat(frames, ignore_index=True)
    bars["timestamp"] = pd.to_datetime(bars["timestamp"], utc=True)
    start = pd.Timestamp(
        datetime.combine(
            research.periods.research_start, datetime.min.time(), tzinfo=UTC
        )
    )
    end = pd.Timestamp(
        datetime.combine(research.periods.research_end, datetime.min.time(), tzinfo=UTC)
    )
    bars = bars[bars["timestamp"].ge(start) & bars["timestamp"].lt(end)]
    bars = bars.sort_values("timestamp", kind="stable").reset_index(drop=True)
    duplicate_timestamps = int(bars["timestamp"].duplicated().sum())
    crossed_closes = int(bars["ask_close"].lt(bars["bid_close"]).sum())
    spread = bars["spread_median_pips"].dropna()

    return {
        "valid": bool(
            len(bars)
            and not missing_months
            and not schema_errors
            and not duplicate_timestamps
            and not crossed_closes
        ),
        "data_root": str(data_root),
        "price_source": research.data.price_source,
        "source_role": research.data.source_role,
        "broker_specific_spread_claim": False,
        "expected_months": list(expected_months),
        "available_months": [month for month in expected_months if month in by_month],
        "missing_months": missing_months,
        "schema_errors": schema_errors,
        "bar_count": len(bars),
        "first_timestamp": bars["timestamp"].min().isoformat(),
        "last_timestamp": bars["timestamp"].max().isoformat(),
        "duplicate_timestamp_count": duplicate_timestamps,
        "crossed_close_count": crossed_closes,
        "spread_median_pips": float(spread.median()),
        "spread_p95_pips": float(spread.quantile(0.95)),
        "spread_max_pips": float(spread.max()),
    }
