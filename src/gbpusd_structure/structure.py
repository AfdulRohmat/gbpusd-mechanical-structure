"""Point-in-time mechanical structure labels used by the Phase-0 audit."""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

import numpy as np
import pandas as pd

from gbpusd_structure.config import StructureConfig


def add_atr(bars: pd.DataFrame, period: int) -> pd.DataFrame:
    """Add simple rolling true-range ATR using completed bars only."""

    if period < 2:
        raise ValueError("ATR period must be at least two")
    frame = bars.sort_values("timestamp", kind="stable").reset_index(drop=True).copy()
    previous_close = frame["mid_close"].shift(1)
    true_range = pd.concat(
        [
            frame["mid_high"] - frame["mid_low"],
            (frame["mid_high"] - previous_close).abs(),
            (frame["mid_low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    frame["true_range"] = true_range
    frame["atr"] = true_range.rolling(period, min_periods=period).mean()
    frame["body_atr"] = (
        (frame["mid_close"] - frame["mid_open"]).abs() / frame["atr"]
    )
    return frame


def eligible_structure_bars(
    bars: pd.DataFrame, minimum_coverage_ratio: float
) -> pd.DataFrame:
    frame = bars.copy()
    frame["structure_eligible"] = (
        frame["coverage_ratio"].ge(minimum_coverage_ratio)
        & frame["atr"].notna()
        & frame["available_at"].gt(frame["timestamp"])
    )
    return frame


def _json_bar_ids(values: pd.Series) -> str:
    return json.dumps(values.astype(str).tolist(), separators=(",", ":"))


def label_swings(
    bars: pd.DataFrame,
    config: StructureConfig,
    *,
    pip_size: float,
    right_bars: int | None = None,
) -> pd.DataFrame:
    """Label strict and equal-price-ambiguous causal pivot highs/lows."""

    left = config.swings.left_bars
    right = right_bars or config.swings.right_bars
    tolerance = config.swings.equal_price_tolerance_pips * pip_size
    records: list[dict[str, Any]] = []
    frame = bars.reset_index(drop=True)
    for index in range(left, len(frame) - right):
        window = frame.iloc[index - left : index + right + 1]
        if not bool(window["structure_eligible"].all()):
            continue
        candidate = frame.iloc[index]
        neighbours = pd.concat(
            [
                frame.iloc[index - left : index],
                frame.iloc[index + 1 : index + right + 1],
            ]
        )
        confirmation = frame.iloc[index + right]
        definitions = (
            (
                "high",
                "up",
                float(candidate["mid_high"]),
                float(neighbours["mid_high"].max()),
            ),
            (
                "low",
                "down",
                float(candidate["mid_low"]),
                float(neighbours["mid_low"].min()),
            ),
        )
        for kind, direction, price, neighbour_extreme in definitions:
            margin = (
                price - neighbour_extreme
                if kind == "high"
                else neighbour_extreme - price
            )
            is_local_extreme = margin >= -1e-12
            if not is_local_extreme:
                continue
            ambiguous = margin <= tolerance + 1e-12
            event_at = candidate["timestamp"]
            available_at = confirmation["available_at"]
            records.append(
                {
                    "event_id": (
                        f"swing:{candidate['timeframe']}:{kind}:"
                        f"{event_at.isoformat()}:r{right}"
                    ),
                    "symbol": "GBPUSD",
                    "timeframe": candidate["timeframe"],
                    "event_type": f"swing_{kind}",
                    "event_at": event_at,
                    "available_at": available_at,
                    "direction": direction,
                    "price": price,
                    "atr": float(candidate["atr"]),
                    "ambiguous_equal": ambiguous,
                    "extreme_margin_pips": margin / pip_size,
                    "pivot_index": index,
                    "confirmation_index": index + right,
                    "bar_id": candidate["bar_id"],
                    "confirmation_bar_id": confirmation["bar_id"],
                    "source_bar_ids": _json_bar_ids(window["bar_id"]),
                    "confirmation_delay_bars": right,
                    "definition_version": (
                        f"swing-l{left}-r{right}-"
                        f"tol{config.swings.equal_price_tolerance_pips:g}pip"
                    ),
                }
            )
    return pd.DataFrame.from_records(records)


def _sequence_regime(
    highs: list[dict[str, Any]],
    lows: list[dict[str, Any]],
    tolerance: float,
) -> str | None:
    if len(highs) < 2 or len(lows) < 2:
        return None
    high_delta = highs[-1]["price"] - highs[-2]["price"]
    low_delta = lows[-1]["price"] - lows[-2]["price"]
    if high_delta > tolerance and low_delta > tolerance:
        return "bullish"
    if high_delta < -tolerance and low_delta < -tolerance:
        return "bearish"
    return None


def label_structure_breaks(
    bars: pd.DataFrame,
    swings: pd.DataFrame,
    config: StructureConfig,
    *,
    pip_size: float,
    break_buffer_atr: float | None = None,
) -> pd.DataFrame:
    """Classify close-confirmed BOS, CHoCH, and unclassified breaks."""

    if swings.empty:
        return pd.DataFrame()
    buffer_ratio = (
        config.breaks.minimum_buffer_atr
        if break_buffer_atr is None
        else break_buffer_atr
    )
    confirmed = swings[~swings["ambiguous_equal"]].copy()
    by_confirmation: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in confirmed.to_dict("records"):
        by_confirmation[int(row["confirmation_index"])].append(row)

    highs: list[dict[str, Any]] = []
    lows: list[dict[str, Any]] = []
    active_high: dict[str, Any] | None = None
    active_low: dict[str, Any] | None = None
    regime = "neutral"
    records: list[dict[str, Any]] = []
    tolerance = config.swings.equal_price_tolerance_pips * pip_size

    for index, bar in bars.reset_index(drop=True).iterrows():
        for swing in by_confirmation.get(index, []):
            if swing["event_type"] == "swing_high":
                highs.append(swing)
                active_high = swing
            else:
                lows.append(swing)
                active_low = swing
        inferred = _sequence_regime(highs, lows, tolerance)
        if inferred is not None:
            regime = inferred
        if not bool(bar["structure_eligible"]) or pd.isna(bar["atr"]):
            continue

        candidates: list[tuple[str, dict[str, Any]]] = []
        buffer = float(bar["atr"]) * buffer_ratio
        close = float(bar["mid_close"])
        if active_high is not None and close > active_high["price"] + buffer:
            candidates.append(("up", active_high))
        if active_low is not None and close < active_low["price"] - buffer:
            candidates.append(("down", active_low))
        for direction, source_swing in candidates:
            if regime == "bullish":
                event_type = "bos" if direction == "up" else "choch"
            elif regime == "bearish":
                event_type = "bos" if direction == "down" else "choch"
            else:
                event_type = "unclassified_break"
            records.append(
                {
                    "event_id": (
                        f"break:{bar['timeframe']}:{direction}:"
                        f"{bar['timestamp'].isoformat()}:b{buffer_ratio:g}"
                    ),
                    "symbol": "GBPUSD",
                    "timeframe": bar["timeframe"],
                    "event_type": event_type,
                    "event_at": bar["timestamp"],
                    "available_at": bar["available_at"],
                    "direction": direction,
                    "regime_before": regime,
                    "broken_swing_id": source_swing["event_id"],
                    "broken_level": source_swing["price"],
                    "close": close,
                    "atr": float(bar["atr"]),
                    "buffer_atr": buffer_ratio,
                    "body_atr": float(bar["body_atr"]),
                    "displacement_qualified": bool(
                        bar["body_atr"]
                        >= config.breaks.displacement_minimum_body_atr
                    ),
                    "bar_id": bar["bar_id"],
                    "source_bar_ids": json.dumps(
                        [source_swing["bar_id"], bar["bar_id"]],
                        separators=(",", ":"),
                    ),
                    "definition_version": f"break-close-buffer{buffer_ratio:g}atr",
                }
            )
            if direction == "up":
                active_high = None
            else:
                active_low = None
            if event_type == "choch":
                regime = "bullish" if direction == "up" else "bearish"
    return pd.DataFrame.from_records(records)


def label_fair_value_gaps(
    bars: pd.DataFrame,
    config: StructureConfig,
    *,
    minimum_size_atr: float | None = None,
) -> pd.DataFrame:
    """Label causal three-candle wick gaps and their later lifecycle."""

    minimum_ratio = (
        config.fair_value_gap.minimum_size_atr
        if minimum_size_atr is None
        else minimum_size_atr
    )
    frame = bars.reset_index(drop=True)
    records: list[dict[str, Any]] = []
    maximum_age = config.fair_value_gap.maximum_age_bars
    for index in range(2, len(frame)):
        first = frame.iloc[index - 2]
        second = frame.iloc[index - 1]
        third = frame.iloc[index]
        if not bool(frame.iloc[index - 2 : index + 1]["structure_eligible"].all()):
            continue
        if first["available_at"] != second["timestamp"]:
            continue
        if second["available_at"] != third["timestamp"]:
            continue
        atr = float(third["atr"])
        definitions = []
        bullish_size = float(third["mid_low"] - first["mid_high"])
        if bullish_size > 0:
            definitions.append(
                ("up", float(first["mid_high"]), float(third["mid_low"]), bullish_size)
            )
        bearish_size = float(first["mid_low"] - third["mid_high"])
        if bearish_size > 0:
            definitions.append(
                (
                    "down",
                    float(third["mid_high"]),
                    float(first["mid_low"]),
                    bearish_size,
                )
            )
        for direction, lower, upper, size in definitions:
            if size < minimum_ratio * atr:
                continue
            partial_at = pd.NaT
            full_at = pd.NaT
            fill_delay: int | None = None
            scan_end = min(len(frame), index + maximum_age + 1)
            for later_index in range(index + 1, scan_end):
                later = frame.iloc[later_index]
                if not bool(later["structure_eligible"]):
                    continue
                if direction == "up":
                    partial = later["mid_low"] < upper
                    full = later["mid_low"] <= lower
                else:
                    partial = later["mid_high"] > lower
                    full = later["mid_high"] >= upper
                if partial and pd.isna(partial_at):
                    partial_at = later["available_at"]
                if full:
                    full_at = later["available_at"]
                    fill_delay = later_index - index
                    break
            observations = len(frame) - index - 1
            if pd.notna(full_at):
                status = "filled"
            elif observations >= maximum_age:
                status = "expired"
            else:
                status = "open_at_sample_end"
            records.append(
                {
                    "event_id": (
                        f"fvg:{third['timeframe']}:{direction}:"
                        f"{third['timestamp'].isoformat()}:m{minimum_ratio:g}"
                    ),
                    "symbol": "GBPUSD",
                    "timeframe": third["timeframe"],
                    "event_type": "fair_value_gap",
                    "event_at": third["timestamp"],
                    "available_at": third["available_at"],
                    "direction": direction,
                    "lower_bound": lower,
                    "upper_bound": upper,
                    "size": size,
                    "size_atr": size / atr,
                    "atr": atr,
                    "partial_fill_at": partial_at,
                    "full_fill_at": full_at,
                    "fill_delay_bars": fill_delay,
                    "status": status,
                    "bar_id": third["bar_id"],
                    "source_bar_ids": json.dumps(
                        [first["bar_id"], second["bar_id"], third["bar_id"]],
                        separators=(",", ":"),
                    ),
                    "definition_version": f"fvg-wick-min{minimum_ratio:g}atr",
                }
            )
    return pd.DataFrame.from_records(records)


def build_support_resistance_zones(
    swings: pd.DataFrame,
    bars: pd.DataFrame,
    config: StructureConfig,
    *,
    cluster_tolerance_atr: float | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Cluster confirmed swing prices into causal S/R zone snapshots."""

    tolerance_ratio = (
        config.support_resistance.cluster_tolerance_atr
        if cluster_tolerance_atr is None
        else cluster_tolerance_atr
    )
    if swings.empty:
        return pd.DataFrame(), pd.DataFrame()
    timeframe = str(bars.iloc[0]["timeframe"])
    accepted = swings[~swings["ambiguous_equal"]].sort_values(
        ["available_at", "event_at"], kind="stable"
    )
    zones: list[dict[str, Any]] = []
    snapshots: list[dict[str, Any]] = []
    next_id = 1
    for swing in accepted.to_dict("records"):
        role = "resistance" if swing["event_type"] == "swing_high" else "support"
        tolerance = float(swing["atr"]) * tolerance_ratio
        if not np.isfinite(tolerance) or tolerance <= 0:
            continue
        candidates = [
            zone
            for zone in zones
            if zone["role"] == role
            and swing["confirmation_index"] - zone["last_touch_index"]
            <= config.support_resistance.maximum_age_bars
            and abs(swing["price"] - zone["center"])
            <= max(tolerance, zone["half_width"])
        ]
        if candidates:
            zone = min(
                candidates,
                key=lambda item: abs(swing["price"] - item["center"]),
            )
            previous_touches = zone["touch_count"]
            zone["center"] = (
                zone["center"] * previous_touches + swing["price"]
            ) / (previous_touches + 1)
            zone["lower_bound"] = min(zone["lower_bound"], swing["price"] - tolerance)
            zone["upper_bound"] = max(zone["upper_bound"], swing["price"] + tolerance)
            zone["half_width"] = max(
                zone["center"] - zone["lower_bound"],
                zone["upper_bound"] - zone["center"],
            )
            zone["touch_count"] += 1
            zone["last_touch_at"] = swing["event_at"]
            zone["last_available_at"] = swing["available_at"]
            zone["last_touch_index"] = swing["confirmation_index"]
            if (
                pd.isna(zone["active_at"])
                and zone["touch_count"]
                >= config.support_resistance.minimum_confirmed_touches
            ):
                zone["active_at"] = swing["available_at"]
        else:
            zone = {
                "zone_id": f"zone:{timeframe}:{role}:{next_id:06d}",
                "symbol": "GBPUSD",
                "timeframe": timeframe,
                "role": role,
                "center": swing["price"],
                "lower_bound": swing["price"] - tolerance,
                "upper_bound": swing["price"] + tolerance,
                "half_width": tolerance,
                "touch_count": 1,
                "created_at": swing["event_at"],
                "created_available_at": swing["available_at"],
                "created_index": swing["confirmation_index"],
                "active_at": pd.NaT,
                "last_touch_at": swing["event_at"],
                "last_available_at": swing["available_at"],
                "last_touch_index": swing["confirmation_index"],
                "definition_version": f"sr-cluster{tolerance_ratio:g}atr",
            }
            zones.append(zone)
            next_id += 1
        snapshots.append(
            {
                "zone_id": zone["zone_id"],
                "symbol": "GBPUSD",
                "timeframe": timeframe,
                "event_type": "zone_touch",
                "event_at": swing["event_at"],
                "available_at": swing["available_at"],
                "direction": swing["direction"],
                "role": role,
                "center": zone["center"],
                "lower_bound": zone["lower_bound"],
                "upper_bound": zone["upper_bound"],
                "touch_count": zone["touch_count"],
                "active": bool(
                    zone["touch_count"]
                    >= config.support_resistance.minimum_confirmed_touches
                ),
                "swing_id": swing["event_id"],
                "source_bar_ids": json.dumps(
                    [swing["bar_id"]], separators=(",", ":")
                ),
                "definition_version": zone["definition_version"],
            }
        )
    final_index = len(bars) - 1
    for zone in zones:
        zone["age_bars_at_sample_end"] = final_index - zone["created_index"]
        zone["bars_since_last_touch"] = final_index - zone["last_touch_index"]
        zone["status_at_sample_end"] = (
            "expired"
            if final_index - zone["last_touch_index"]
            > config.support_resistance.maximum_age_bars
            else "active_or_candidate"
        )
    return pd.DataFrame.from_records(zones), pd.DataFrame.from_records(snapshots)
