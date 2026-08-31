"""Causal price-action state and setup primitives for Phase 3."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

import numpy as np
import pandas as pd

from gbpusd_structure.config import ProjectConfig
from gbpusd_structure.structure import add_atr

TREND_UP_STATES = {"trend_up_active", "trend_up_break_pending_extreme"}
TREND_DOWN_STATES = {"trend_down_active", "trend_down_break_pending_extreme"}
RANGE_STATES = {
    "range",
    "range_break_up_pending",
    "range_break_down_pending",
    "range_break_up_wait_retest",
    "range_break_down_wait_retest",
}


def prepare_m5_bars(m5: pd.DataFrame, config: ProjectConfig) -> pd.DataFrame:
    """Add causal bar availability, ATR, EMA, and audit identifiers to M5."""

    frame = m5.sort_values("timestamp", kind="stable").reset_index(drop=True).copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    frame["available_at"] = frame["timestamp"] + pd.Timedelta(5, unit="min")
    frame["timeframe"] = "5min"
    frame["bar_id"] = frame["timestamp"].map(lambda value: f"5min:{value.isoformat()}")
    frame["coverage_ratio"] = 1.0
    frame = add_atr(frame, config.structure.volatility.atr_period)
    frame["structure_eligible"] = (
        frame["atr"].notna()
        & frame["tick_count"].gt(0)
        & frame["available_at"].gt(frame["timestamp"])
    )
    frame["ema21"] = (
        frame["mid_close"]
        .ewm(
            span=config.phase3.m5_setup.ema_period,
            adjust=False,
            min_periods=config.phase3.m5_setup.ema_period,
        )
        .mean()
    )
    return frame


def add_m15_ema(m15: pd.DataFrame, config: ProjectConfig) -> pd.DataFrame:
    frame = m15.copy()
    frame["ema21"] = (
        frame["mid_close"]
        .ewm(
            span=config.phase3.m5_setup.ema_period,
            adjust=False,
            min_periods=config.phase3.m5_setup.ema_period,
        )
        .mean()
    )
    return frame


def _raw_trend(
    latest_high: dict[str, Any] | None,
    latest_low: dict[str, Any] | None,
) -> str | None:
    if latest_high is None or latest_low is None:
        return None
    high_relation = latest_high["structural_relationship"]
    low_relation = latest_low["structural_relationship"]
    if high_relation == "HH" and low_relation == "HL":
        return "up"
    if high_relation == "LH" and low_relation == "LL":
        return "down"
    return None


def _trendline(
    confirmed_by_kind: dict[str, list[dict[str, Any]]],
    direction: str,
    bar_index: int,
) -> dict[str, Any] | None:
    kind = "low" if direction == "up" else "high"
    candidates = confirmed_by_kind[kind]
    if len(candidates) < 2:
        return None
    first, second = candidates[-2:]
    first_index = int(first["pivot_index"])
    second_index = int(second["pivot_index"])
    if second_index <= first_index:
        return None
    first_price = float(first["price"])
    second_price = float(second["price"])
    if direction == "up" and second_price <= first_price:
        return None
    if direction == "down" and second_price >= first_price:
        return None
    slope = (second_price - first_price) / (second_index - first_index)
    value = second_price + slope * (bar_index - second_index)
    return {
        "direction": direction,
        "first_id": first["event_id"],
        "second_id": second["event_id"],
        "anchors_available_at": max(
            pd.Timestamp(first["available_at"]),
            pd.Timestamp(second["available_at"]),
        ),
        "slope_per_bar": slope,
        "value_at_bar_start": value,
        "value_at_bar_available": value + slope,
    }


def _range_candidate(
    bars: pd.DataFrame,
    index: int,
    confirmed: list[dict[str, Any]],
    config: ProjectConfig,
) -> dict[str, Any] | None:
    settings = config.phase3.m15_regime
    start = index - settings.range_window_bars + 1
    if start < 0:
        return None
    window = bars.iloc[start : index + 1]
    if not bool(window["structure_eligible"].all()):
        return None
    atr = float(bars.iloc[index]["atr"])
    if not np.isfinite(atr) or atr <= 0:
        return None
    available = pd.Timestamp(bars.iloc[index]["available_at"])
    swings = [
        swing
        for swing in confirmed
        if int(swing["pivot_index"]) >= start
        and int(swing["pivot_index"]) <= index
        and pd.Timestamp(swing["available_at"]) <= available
    ]
    highs = [
        float(item["price"]) for item in swings if item["event_type"] == "swing_high"
    ]
    lows = [
        float(item["price"]) for item in swings if item["event_type"] == "swing_low"
    ]
    minimum = settings.range_minimum_swing_touches_per_side
    if len(highs) < minimum or len(lows) < minimum:
        return None
    tolerance = settings.range_boundary_cluster_tolerance_atr * atr
    if max(highs) - min(highs) > tolerance or max(lows) - min(lows) > tolerance:
        return None
    upper = float(np.median(highs))
    lower = float(np.median(lows))
    width_atr = (upper - lower) / atr
    if (
        not settings.range_width_minimum_atr
        <= width_atr
        <= settings.range_width_maximum_atr
    ):
        return None
    closes = window["mid_close"].to_numpy(dtype="float64")
    traveled = float(np.abs(np.diff(closes)).sum())
    efficiency = abs(float(closes[-1] - closes[0])) / traveled if traveled else 0.0
    if efficiency > settings.range_efficiency_maximum:
        return None
    return {
        "lower": lower,
        "upper": upper,
        "width_atr": width_atr,
        "efficiency": efficiency,
        "high_touch_count": len(highs),
        "low_touch_count": len(lows),
        "source_swing_ids": [item["event_id"] for item in swings],
        "source_available_at": max(
            pd.Timestamp(item["available_at"]) for item in swings
        ),
        "window_start_at": pd.Timestamp(window.iloc[0]["timestamp"]),
    }


def _transition_record(
    *,
    bar: pd.Series,
    previous: str,
    state: str,
    cause: str,
    direction: str | None,
    range_id: str | None,
    lower: float | None,
    upper: float | None,
) -> dict[str, Any]:
    return {
        "transition_id": (
            f"pa:{bar['timestamp'].isoformat()}:{previous}:{state}:{cause}"
        ),
        "event_at": pd.Timestamp(bar["timestamp"]),
        "available_at": pd.Timestamp(bar["available_at"]),
        "previous_state": previous,
        "state": state,
        "cause": cause,
        "direction": direction,
        "range_id": range_id,
        "range_lower": lower,
        "range_upper": upper,
    }


def build_m15_price_action_states(
    m15: pd.DataFrame,
    swings: pd.DataFrame,
    config: ProjectConfig,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Build the preregistered causal M15 regime and breakout lifecycles."""

    bars = add_m15_ema(m15.reset_index(drop=True), config)
    swing_records = swings.sort_values(
        ["available_at", "event_id"], kind="stable"
    ).to_dict("records")
    by_available: dict[pd.Timestamp, list[dict[str, Any]]] = defaultdict(list)
    for swing in swing_records:
        by_available[pd.Timestamp(swing["available_at"])].append(swing)

    confirmed: list[dict[str, Any]] = []
    confirmed_by_kind: dict[str, list[dict[str, Any]]] = {
        "high": [],
        "low": [],
    }
    latest_high: dict[str, Any] | None = None
    latest_low: dict[str, Any] | None = None
    state = "undetermined"
    trend_extreme: float | None = None
    pending_extreme: float | None = None
    range_id: str | None = None
    range_lower: float | None = None
    range_upper: float | None = None
    range_started_index: int | None = None
    breakout_started_index: int | None = None
    breakout_closes = 0
    snapshots: list[dict[str, Any]] = []
    transitions: list[dict[str, Any]] = []
    context_events: list[dict[str, Any]] = []
    settings = config.phase3.m15_regime

    for index, bar in bars.iterrows():
        previous_state = state
        close = float(bar["mid_close"])
        high = float(bar["mid_high"])
        low = float(bar["mid_low"])
        atr = float(bar["atr"]) if pd.notna(bar["atr"]) else np.nan
        eligible = bool(bar["structure_eligible"]) and np.isfinite(atr) and atr > 0

        line_direction = (
            "up"
            if state in TREND_UP_STATES
            else "down"
            if state in TREND_DOWN_STATES
            else None
        )
        line = (
            _trendline(confirmed_by_kind, line_direction, index)
            if line_direction
            else None
        )
        cause: str | None = None
        transition_direction: str | None = None

        if eligible and state == "trend_up_active":
            trend_extreme = high if trend_extreme is None else max(trend_extreme, high)
            if (
                line
                and close
                < line["value_at_bar_start"] - settings.trendline_break_buffer_atr * atr
            ):
                pending_extreme = trend_extreme
                state = "trend_up_break_pending_extreme"
                cause = "uptrendline_close_break"
                transition_direction = "long"
        elif eligible and state == "trend_down_active":
            trend_extreme = low if trend_extreme is None else min(trend_extreme, low)
            if (
                line
                and close
                > line["value_at_bar_start"] + settings.trendline_break_buffer_atr * atr
            ):
                pending_extreme = trend_extreme
                state = "trend_down_break_pending_extreme"
                cause = "downtrendline_close_break"
                transition_direction = "short"
        elif eligible and state == "trend_up_break_pending_extreme":
            tolerance = settings.final_extreme_near_equal_tolerance_atr * atr
            if pending_extreme is not None and high >= pending_extreme - tolerance:
                state = "post_up_extreme_transition"
                cause = "up_final_extreme_fulfilled"
                transition_direction = "long"
        elif eligible and state == "trend_down_break_pending_extreme":
            tolerance = settings.final_extreme_near_equal_tolerance_atr * atr
            if pending_extreme is not None and low <= pending_extreme + tolerance:
                state = "post_down_extreme_transition"
                cause = "down_final_extreme_fulfilled"
                transition_direction = "short"
        elif (
            eligible
            and state == "range"
            and range_lower is not None
            and range_upper is not None
        ):
            buffer = settings.range_breakout_buffer_atr * atr
            if close > range_upper + buffer:
                state = "range_break_up_pending"
                breakout_started_index = index
                breakout_closes = 1
                cause = "range_close_break_up"
                transition_direction = "long"
            elif close < range_lower - buffer:
                state = "range_break_down_pending"
                breakout_started_index = index
                breakout_closes = 1
                cause = "range_close_break_down"
                transition_direction = "short"
        elif eligible and state in {
            "range_break_up_pending",
            "range_break_down_pending",
        }:
            assert range_lower is not None and range_upper is not None
            assert breakout_started_index is not None
            age = index - breakout_started_index
            upward = state == "range_break_up_pending"
            inside = close <= range_upper if upward else close >= range_lower
            boundary = range_upper if upward else range_lower
            direction = "short" if upward else "long"
            if inside:
                context_events.append(
                    {
                        "event_id": (
                            f"failed_range_break:{bar['timestamp'].isoformat()}"
                        ),
                        "event_type": "failed_range_break",
                        "event_at": pd.Timestamp(bar["timestamp"]),
                        "available_at": pd.Timestamp(bar["available_at"]),
                        "direction": direction,
                        "range_id": range_id,
                        "range_lower": range_lower,
                        "range_upper": range_upper,
                        "key_boundary": boundary,
                        "atr": atr,
                    }
                )
                state = "range"
                cause = "range_break_reentered"
                transition_direction = direction
                breakout_started_index = None
                breakout_closes = 0
            else:
                buffer = settings.range_breakout_buffer_atr * atr
                still_outside = (
                    close > range_upper + buffer
                    if upward
                    else close < range_lower - buffer
                )
                breakout_closes = breakout_closes + 1 if still_outside else 0
                if breakout_closes >= settings.range_acceptance_consecutive_closes:
                    state = (
                        "range_break_up_wait_retest"
                        if upward
                        else "range_break_down_wait_retest"
                    )
                    cause = "range_break_accepted"
                    transition_direction = "long" if upward else "short"
                    breakout_started_index = index
                elif age > settings.range_resolution_bars:
                    state = "undetermined"
                    cause = "range_break_pending_expired"
                    range_id = None
                    range_lower = None
                    range_upper = None
                    breakout_started_index = None
                    breakout_closes = 0
        elif eligible and state in {
            "range_break_up_wait_retest",
            "range_break_down_wait_retest",
        }:
            assert range_lower is not None and range_upper is not None
            assert breakout_started_index is not None
            age = index - breakout_started_index
            upward = state == "range_break_up_wait_retest"
            boundary = range_upper if upward else range_lower
            reentered = close <= range_upper if upward else close >= range_lower
            tolerance = settings.range_retest_tolerance_atr * atr
            touched = (
                low <= boundary + tolerance if upward else high >= boundary - tolerance
            )
            held = close > boundary if upward else close < boundary
            if reentered:
                state = "range"
                cause = "accepted_break_reentered_range"
                transition_direction = "short" if upward else "long"
                breakout_started_index = None
                breakout_closes = 0
            elif touched and held:
                direction = "long" if upward else "short"
                context_events.append(
                    {
                        "event_id": (
                            "accepted_breakout_pullback:"
                            f"{bar['timestamp'].isoformat()}"
                        ),
                        "event_type": "accepted_breakout_pullback",
                        "event_at": pd.Timestamp(bar["timestamp"]),
                        "available_at": pd.Timestamp(bar["available_at"]),
                        "direction": direction,
                        "range_id": range_id,
                        "range_lower": range_lower,
                        "range_upper": range_upper,
                        "key_boundary": boundary,
                        "atr": atr,
                    }
                )
                state = "trend_up_active" if upward else "trend_down_active"
                trend_extreme = high if upward else low
                pending_extreme = None
                cause = "accepted_breakout_retest_held"
                transition_direction = direction
                range_id = None
                range_lower = None
                range_upper = None
                breakout_started_index = None
                breakout_closes = 0
            elif age > settings.range_resolution_bars:
                state = "undetermined"
                cause = "accepted_break_retest_expired"
                range_id = None
                range_lower = None
                range_upper = None
                breakout_started_index = None
                breakout_closes = 0

        for swing in by_available.get(pd.Timestamp(bar["available_at"]), []):
            confirmed.append(swing)
            if swing["event_type"] == "swing_high":
                latest_high = swing
                confirmed_by_kind["high"].append(swing)
            else:
                latest_low = swing
                confirmed_by_kind["low"].append(swing)
        raw_trend = _raw_trend(latest_high, latest_low)
        candidate = (
            _range_candidate(bars, index, confirmed, config) if eligible else None
        )

        if eligible and cause is None:
            if state == "undetermined":
                if raw_trend == "up":
                    state = "trend_up_active"
                    trend_extreme = high
                    cause = "proven_hh_hl"
                    transition_direction = "long"
                elif raw_trend == "down":
                    state = "trend_down_active"
                    trend_extreme = low
                    cause = "proven_lh_ll"
                    transition_direction = "short"
                elif candidate:
                    state = "range"
                    range_id = f"range:{bar['available_at'].isoformat()}"
                    range_lower = candidate["lower"]
                    range_upper = candidate["upper"]
                    range_started_index = index
                    cause = "causal_range_confirmed"
            elif state in {
                "post_up_extreme_transition",
                "post_down_extreme_transition",
            }:
                if raw_trend == "up":
                    state = "trend_up_active"
                    trend_extreme = high
                    pending_extreme = None
                    cause = "uptrend_reproven"
                    transition_direction = "long"
                elif raw_trend == "down":
                    state = "trend_down_active"
                    trend_extreme = low
                    pending_extreme = None
                    cause = "downtrend_reproven"
                    transition_direction = "short"
                elif candidate:
                    state = "range"
                    range_id = f"range:{bar['available_at'].isoformat()}"
                    range_lower = candidate["lower"]
                    range_upper = candidate["upper"]
                    range_started_index = index
                    pending_extreme = None
                    cause = "post_extreme_range_confirmed"
            elif state == "trend_up_break_pending_extreme" and raw_trend == "down":
                state = "trend_down_active"
                trend_extreme = low
                pending_extreme = None
                cause = "opposite_downtrend_overrode_pending_extreme"
                transition_direction = "short"
            elif state == "trend_down_break_pending_extreme" and raw_trend == "up":
                state = "trend_up_active"
                trend_extreme = high
                pending_extreme = None
                cause = "opposite_uptrend_overrode_pending_extreme"
                transition_direction = "long"
            elif state == "trend_up_active" and raw_trend == "down":
                state = "trend_down_active"
                trend_extreme = low
                pending_extreme = None
                cause = "opposite_downtrend_proven"
                transition_direction = "short"
            elif state == "trend_down_active" and raw_trend == "up":
                state = "trend_up_active"
                trend_extreme = high
                pending_extreme = None
                cause = "opposite_uptrend_proven"
                transition_direction = "long"

        if state != previous_state:
            transitions.append(
                _transition_record(
                    bar=bar,
                    previous=previous_state,
                    state=state,
                    cause=cause or "state_change",
                    direction=transition_direction,
                    range_id=range_id,
                    lower=range_lower,
                    upper=range_upper,
                )
            )

        snapshot_line_direction = (
            "up"
            if state in TREND_UP_STATES
            else "down"
            if state in TREND_DOWN_STATES
            else None
        )
        snapshot_line = (
            _trendline(confirmed_by_kind, snapshot_line_direction, index)
            if snapshot_line_direction
            else None
        )
        snapshots.append(
            {
                "bar_id": bar["bar_id"],
                "timestamp": pd.Timestamp(bar["timestamp"]),
                "available_at": pd.Timestamp(bar["available_at"]),
                "structure_eligible": bool(bar["structure_eligible"]),
                "state": state,
                "raw_trend": raw_trend,
                "directional_bias": (
                    "long"
                    if state in TREND_UP_STATES
                    else "short"
                    if state in TREND_DOWN_STATES
                    else None
                ),
                "atr": atr,
                "ema21": float(bar["ema21"]) if pd.notna(bar["ema21"]) else None,
                "trend_extreme": trend_extreme,
                "pending_extreme": pending_extreme,
                "trendline_direction": snapshot_line_direction,
                "trendline_value_at_available": (
                    snapshot_line["value_at_bar_available"] if snapshot_line else None
                ),
                "trendline_slope_per_minute": (
                    snapshot_line["slope_per_bar"] / 15 if snapshot_line else None
                ),
                "trendline_anchor_1": snapshot_line["first_id"]
                if snapshot_line
                else None,
                "trendline_anchor_2": snapshot_line["second_id"]
                if snapshot_line
                else None,
                "trendline_anchors_available_at": (
                    snapshot_line["anchors_available_at"] if snapshot_line else pd.NaT
                ),
                "range_id": range_id,
                "range_lower": range_lower,
                "range_upper": range_upper,
                "range_started_index": range_started_index,
            }
        )

    return (
        pd.DataFrame.from_records(snapshots),
        pd.DataFrame.from_records(transitions),
        pd.DataFrame.from_records(context_events),
    )


def signal_bar_quality(
    bar: pd.Series | dict[str, Any],
    direction: str,
    config: ProjectConfig,
) -> tuple[bool, dict[str, float]]:
    """Apply the frozen body, close-location, and normalized-range rule."""

    high = float(bar["mid_high"])
    low = float(bar["mid_low"])
    open_price = float(bar["mid_open"])
    close = float(bar["mid_close"])
    atr = float(bar["atr"])
    total_range = high - low
    if total_range <= 0 or not np.isfinite(atr) or atr <= 0:
        return False, {"body_fraction": 0.0, "close_location": 0.5, "range_atr": 0.0}
    body_fraction = abs(close - open_price) / total_range
    close_location = (close - low) / total_range
    range_atr = total_range / atr
    settings = config.phase3.m5_setup
    directional = close > open_price if direction == "long" else close < open_price
    location_pass = (
        close_location >= settings.signal_bar_minimum_close_location
        if direction == "long"
        else close_location <= 1 - settings.signal_bar_minimum_close_location
    )
    passed = bool(
        directional
        and body_fraction >= settings.signal_bar_minimum_body_fraction
        and location_pass
        and range_atr >= settings.signal_bar_minimum_range_m5_atr
    )
    return passed, {
        "body_fraction": body_fraction,
        "close_location": close_location,
        "range_atr": range_atr,
    }


def adjacent_overlap_ratio(first: pd.Series, second: pd.Series) -> float:
    overlap = max(
        0.0,
        min(float(first["mid_high"]), float(second["mid_high"]))
        - max(float(first["mid_low"]), float(second["mid_low"])),
    )
    denominator = min(
        float(first["mid_high"] - first["mid_low"]),
        float(second["mid_high"] - second["mid_low"]),
    )
    return overlap / denominator if denominator > 0 else 0.0


def congestion_status(
    bars: pd.DataFrame,
    position: int,
    config: ProjectConfig,
) -> tuple[bool, float | None, float | None]:
    settings = config.phase3.congestion_veto
    start = position - settings.lookback_m5_bars + 1
    if start < 0:
        return False, None, None
    window = bars.iloc[start : position + 1]
    atr = float(bars.iloc[position]["atr"])
    if not np.isfinite(atr) or atr <= 0:
        return False, None, None
    total_range_atr = (
        float(window["mid_high"].max()) - float(window["mid_low"].min())
    ) / atr
    overlaps = [
        adjacent_overlap_ratio(window.iloc[index - 1], window.iloc[index])
        for index in range(1, len(window))
    ]
    mean_overlap = float(np.mean(overlaps)) if overlaps else 0.0
    veto = bool(
        total_range_atr <= settings.maximum_total_range_m5_atr
        and mean_overlap >= settings.minimum_mean_adjacent_overlap
    )
    return veto, total_range_atr, mean_overlap
