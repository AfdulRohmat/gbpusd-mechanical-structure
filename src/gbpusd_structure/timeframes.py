"""Causal multi-timeframe aggregation anchored to the New York FX day."""

from __future__ import annotations

from typing import Literal

import pandas as pd

Timeframe = Literal["15min", "1H", "4H", "1D"]
TIMEFRAME_MINUTES: dict[Timeframe, int] = {
    "15min": 15,
    "1H": 60,
    "4H": 240,
    "1D": 1440,
}


def fx_trading_week_mask(
    timestamps: pd.Series,
    *,
    timezone: str = "America/New_York",
    boundary_hour: int = 17,
) -> pd.Series:
    """Keep timestamps belonging to Monday-Friday FX session dates."""

    utc = pd.to_datetime(timestamps, utc=True)
    local_naive = utc.dt.tz_convert(timezone).dt.tz_localize(None)
    session_date = local_naive + pd.Timedelta(24 - boundary_hour, unit="h")
    return session_date.dt.dayofweek.lt(5)


def _localize_civil(values: pd.Series, timezone: str) -> pd.Series:
    try:
        return values.dt.tz_localize(timezone, ambiguous="infer", nonexistent="raise")
    except ValueError:
        return values.dt.tz_localize(
            timezone, ambiguous=False, nonexistent="shift_forward"
        )


def fx_anchored_boundaries(
    timestamps: pd.Series,
    timeframe: Timeframe,
    *,
    timezone: str = "America/New_York",
    boundary_hour: int = 17,
) -> tuple[pd.Series, pd.Series]:
    """Return UTC start/end boundaries aligned to a local civil FX day."""

    if timeframe not in TIMEFRAME_MINUTES:
        raise ValueError(f"Unsupported timeframe: {timeframe}")
    utc = pd.to_datetime(timestamps, utc=True)
    local_naive = utc.dt.tz_convert(timezone).dt.tz_localize(None)
    shift = pd.Timedelta(boundary_hour, unit="h")
    shifted = local_naive - shift
    minutes = TIMEFRAME_MINUTES[timeframe]
    frequency = "D" if timeframe == "1D" else f"{minutes}min"
    starts_naive = shifted.dt.floor(frequency) + shift
    ends_naive = starts_naive + pd.Timedelta(minutes, unit="min")
    starts = _localize_civil(starts_naive, timezone).dt.tz_convert("UTC")
    ends = _localize_civil(ends_naive, timezone).dt.tz_convert("UTC")
    return starts, ends


def aggregate_m5(
    m5: pd.DataFrame,
    timeframe: Timeframe,
    *,
    timezone: str = "America/New_York",
    boundary_hour: int = 17,
) -> pd.DataFrame:
    """Aggregate canonical M5 Bid/Ask bars without filling missing source bars."""

    if m5.empty:
        raise ValueError("Cannot aggregate empty M5 bars")
    price_columns = {
        f"{side}_{field}"
        for side in ("bid", "ask", "mid")
        for field in ("open", "high", "low", "close")
    }
    required = {
        "timestamp",
        "tick_count",
        "activity_count",
        "spread_open_pips",
        "spread_median_pips",
        "spread_p95_pips",
        "spread_max_pips",
        *price_columns,
    }
    missing = sorted(required.difference(m5.columns))
    if missing:
        raise ValueError("M5 aggregation missing column(s): " + ", ".join(missing))
    frame = m5.sort_values("timestamp", kind="stable").copy()
    frame = frame[
        fx_trading_week_mask(
            frame["timestamp"],
            timezone=timezone,
            boundary_hour=boundary_hour,
        )
    ].copy()
    if frame.empty:
        raise ValueError("M5 bars contain no weekday FX-session observations")
    starts, ends = fx_anchored_boundaries(
        frame["timestamp"],
        timeframe,
        timezone=timezone,
        boundary_hour=boundary_hour,
    )
    frame["_bucket_start"] = starts
    frame["_bucket_end"] = ends
    grouped = frame.groupby(
        ["_bucket_start", "_bucket_end"], sort=True, observed=True
    )

    aggregations: dict[str, tuple[str, str]] = {}
    for side in ("bid", "ask", "mid"):
        aggregations[f"{side}_open"] = (f"{side}_open", "first")
        aggregations[f"{side}_high"] = (f"{side}_high", "max")
        aggregations[f"{side}_low"] = (f"{side}_low", "min")
        aggregations[f"{side}_close"] = (f"{side}_close", "last")
    aggregations.update(
        {
            "tick_count": ("tick_count", "sum"),
            "activity_count": ("activity_count", "sum"),
            "spread_open_pips": ("spread_open_pips", "first"),
            "spread_median_pips": ("spread_median_pips", "median"),
            "spread_p95_pips": ("spread_p95_pips", "max"),
            "spread_max_pips": ("spread_max_pips", "max"),
            "source_m5_count": ("timestamp", "size"),
            "first_source_timestamp": ("timestamp", "min"),
            "last_source_timestamp": ("timestamp", "max"),
        }
    )
    for optional in (
        "up_quote_count",
        "down_quote_count",
        "flat_quote_count",
        "bid_change_count",
        "ask_change_count",
    ):
        if optional in frame:
            aggregations[optional] = (optional, "sum")

    bars = grouped.agg(**aggregations).reset_index()
    bars = bars.rename(
        columns={"_bucket_start": "timestamp", "_bucket_end": "available_at"}
    )
    elapsed_minutes = (
        bars["available_at"] - bars["timestamp"]
    ).dt.total_seconds() / 60
    bars["expected_m5_count"] = (elapsed_minutes / 5).round().astype("int16")
    bars["coverage_ratio"] = bars["source_m5_count"] / bars["expected_m5_count"]
    bars["timeframe"] = timeframe
    bars["bar_id"] = bars["timestamp"].map(
        lambda value: f"{timeframe}:{value.isoformat()}"
    )
    ordered = [
        "bar_id",
        "timeframe",
        "timestamp",
        "available_at",
        *(
            f"{side}_{field}"
            for side in ("bid", "ask", "mid")
            for field in ("open", "high", "low", "close")
        ),
        "tick_count",
        "activity_count",
        "spread_open_pips",
        "spread_median_pips",
        "spread_p95_pips",
        "spread_max_pips",
        "source_m5_count",
        "expected_m5_count",
        "coverage_ratio",
        "first_source_timestamp",
        "last_source_timestamp",
    ]
    ordered.extend(column for column in aggregations if column not in ordered)
    return bars[list(dict.fromkeys(ordered))]


def build_timeframes(m5: pd.DataFrame) -> dict[Timeframe, pd.DataFrame]:
    return {
        timeframe: aggregate_m5(m5, timeframe)
        for timeframe in ("15min", "1H", "4H", "1D")
    }
