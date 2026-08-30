"""Causal Order Block formation and lifecycle labels for Phase 0.2."""

from __future__ import annotations

import json
from typing import Any, Literal

import pandas as pd

from gbpusd_structure.config import StructureConfig

ZoneGeometry = Literal["full_wick_range", "body_range"]


def _candidate_bounds(
    candidate: pd.Series,
    geometry: ZoneGeometry,
) -> tuple[float, float]:
    if geometry == "full_wick_range":
        return float(candidate["mid_low"]), float(candidate["mid_high"])
    if geometry == "body_range":
        return (
            float(min(candidate["mid_open"], candidate["mid_close"])),
            float(max(candidate["mid_open"], candidate["mid_close"])),
        )
    raise ValueError(f"Unsupported Order Block geometry: {geometry}")


def _find_candidate(
    bars: pd.DataFrame,
    anchor_index: int,
    direction: str,
    lookback_bars: int,
) -> tuple[int, pd.Series] | None:
    start = max(0, anchor_index - lookback_bars)
    for index in range(anchor_index - 1, start - 1, -1):
        candidate = bars.iloc[index]
        if not bool(candidate["structure_eligible"]):
            continue
        open_price = float(candidate["mid_open"])
        close_price = float(candidate["mid_close"])
        opposing = (
            direction == "up" and close_price < open_price
        ) or (
            direction == "down" and close_price > open_price
        )
        if opposing:
            return index, candidate
    return None


def _lifecycle(
    bars: pd.DataFrame,
    anchor_index: int,
    direction: str,
    lower_bound: float,
    upper_bound: float,
    maximum_age_bars: int,
) -> dict[str, Any]:
    midpoint = (lower_bound + upper_bound) / 2
    first_touch_at = pd.NaT
    midpoint_touch_at = pd.NaT
    full_mitigation_at = pd.NaT
    invalidation_at = pd.NaT
    terminal_delay_bars: int | None = None
    scan_end = min(len(bars), anchor_index + maximum_age_bars + 1)

    for later_index in range(anchor_index + 1, scan_end):
        later = bars.iloc[later_index]
        if not bool(later["structure_eligible"]):
            continue
        low = float(later["mid_low"])
        high = float(later["mid_high"])
        close = float(later["mid_close"])
        available_at = later["available_at"]
        touched = low <= upper_bound and high >= lower_bound
        midpoint_touched = (
            low <= midpoint if direction == "up" else high >= midpoint
        )
        fully_mitigated = (
            low <= lower_bound if direction == "up" else high >= upper_bound
        )
        invalidated = (
            close < lower_bound if direction == "up" else close > upper_bound
        )
        if touched and pd.isna(first_touch_at):
            first_touch_at = available_at
        if midpoint_touched and pd.isna(midpoint_touch_at):
            midpoint_touch_at = available_at
        if fully_mitigated and pd.isna(full_mitigation_at):
            full_mitigation_at = available_at
        if invalidated:
            invalidation_at = available_at
            terminal_delay_bars = later_index - anchor_index
            break
        if fully_mitigated:
            terminal_delay_bars = later_index - anchor_index
            break

    observations = min(maximum_age_bars, len(bars) - anchor_index - 1)
    if pd.notna(invalidation_at):
        status = "invalidated"
    elif pd.notna(full_mitigation_at):
        status = "fully_mitigated"
    elif observations >= maximum_age_bars:
        status = "expired"
    else:
        status = "active_at_sample_end"
    return {
        "first_touch_at": first_touch_at,
        "midpoint_touch_at": midpoint_touch_at,
        "full_mitigation_at": full_mitigation_at,
        "invalidation_at": invalidation_at,
        "terminal_delay_bars": terminal_delay_bars,
        "observed_bars": observations,
        "status": status,
    }


def label_order_blocks(
    bars: pd.DataFrame,
    breaks: pd.DataFrame,
    gaps: pd.DataFrame,
    config: StructureConfig,
    *,
    pip_size: float,
    candidate_lookback_bars: int | None = None,
    maximum_age_bars: int | None = None,
    zone_geometry: ZoneGeometry | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Create causal Order Block zones and an audit row for every anchor."""

    order_block = config.order_block
    if not order_block.enabled or bars.empty or breaks.empty:
        return pd.DataFrame(), pd.DataFrame()
    timeframe = str(bars.iloc[0]["timeframe"])
    if timeframe not in order_block.source_timeframes:
        return pd.DataFrame(), pd.DataFrame()

    lookback = candidate_lookback_bars or order_block.candidate_lookback_bars
    maximum_age = maximum_age_bars or order_block.maximum_age_bars
    geometry = zone_geometry or order_block.zone_geometry
    frame = bars.reset_index(drop=True)
    bar_index = {
        str(bar_id): index for index, bar_id in enumerate(frame["bar_id"])
    }
    eligible_anchors = breaks[
        breaks["event_type"].isin(order_block.anchor_event_types)
        & breaks["displacement_qualified"]
    ].sort_values(["available_at", "event_at"], kind="stable")
    fvg_lookup: dict[tuple[pd.Timestamp, str], list[str]] = {}
    if not gaps.empty:
        for (event_at, direction), group in gaps.groupby(
            ["event_at", "direction"], observed=True
        ):
            fvg_lookup[(event_at, direction)] = group["event_id"].astype(str).tolist()

    records: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    used_candidates: set[tuple[str, str]] = set()
    for anchor in eligible_anchors.to_dict("records"):
        direction = str(anchor["direction"])
        anchor_index = bar_index.get(str(anchor["bar_id"]))
        diagnostic: dict[str, Any] = {
            "event_id": f"ob-anchor:{anchor['event_id']}:lb{lookback}",
            "symbol": "GBPUSD",
            "timeframe": timeframe,
            "event_type": "order_block_anchor_audit",
            "event_at": anchor["event_at"],
            "available_at": anchor["available_at"],
            "direction": direction,
            "anchor_break_id": anchor["event_id"],
            "anchor_event_type": anchor["event_type"],
            "candidate_found": False,
            "candidate_bar_id": None,
            "status": "missing_anchor_bar",
            "source_bar_ids": json.dumps([anchor["bar_id"]], separators=(",", ":")),
            "definition_version": f"ob-anchor-lookback{lookback}",
        }
        if anchor_index is None:
            diagnostics.append(diagnostic)
            continue
        found = _find_candidate(frame, anchor_index, direction, lookback)
        if found is None:
            diagnostic["status"] = "no_opposing_candle"
            diagnostics.append(diagnostic)
            continue

        candidate_index, candidate = found
        candidate_key = (direction, str(candidate["bar_id"]))
        diagnostic["candidate_found"] = True
        diagnostic["candidate_bar_id"] = candidate["bar_id"]
        if candidate_key in used_candidates:
            diagnostic["status"] = "duplicate_candidate"
            diagnostics.append(diagnostic)
            continue
        used_candidates.add(candidate_key)
        diagnostic["status"] = "created"
        diagnostics.append(diagnostic)

        lower_bound, upper_bound = _candidate_bounds(candidate, geometry)
        same_bar_fvgs = fvg_lookup.get(
            (anchor["event_at"], direction),
            [],
        )
        prior_overlaps = [
            prior
            for prior in records
            if prior["lower_bound"] <= upper_bound
            and prior["upper_bound"] >= lower_bound
        ]
        nested_count = sum(
            (
                prior["lower_bound"] <= lower_bound
                and prior["upper_bound"] >= upper_bound
            )
            or (
                lower_bound <= prior["lower_bound"]
                and upper_bound >= prior["upper_bound"]
            )
            for prior in prior_overlaps
        )
        lifecycle = _lifecycle(
            frame,
            anchor_index,
            direction,
            lower_bound,
            upper_bound,
            maximum_age,
        )
        records.append(
            {
                "event_id": (
                    f"order-block:{timeframe}:{direction}:"
                    f"{candidate['timestamp'].isoformat()}"
                ),
                "symbol": "GBPUSD",
                "timeframe": timeframe,
                "event_type": "order_block",
                "event_at": anchor["event_at"],
                "available_at": anchor["available_at"],
                "direction": direction,
                "anchor_break_id": anchor["event_id"],
                "anchor_event_type": anchor["event_type"],
                "candidate_at": candidate["timestamp"],
                "candidate_available_at": candidate["available_at"],
                "candidate_bar_id": candidate["bar_id"],
                "candidate_index": candidate_index,
                "anchor_index": anchor_index,
                "candidate_to_anchor_bars": anchor_index - candidate_index,
                "lower_bound": lower_bound,
                "upper_bound": upper_bound,
                "midpoint": (lower_bound + upper_bound) / 2,
                "width_pips": (upper_bound - lower_bound) / pip_size,
                "zone_geometry": geometry,
                "fvg_confluent": bool(same_bar_fvgs),
                "fvg_event_ids": json.dumps(same_bar_fvgs, separators=(",", ":")),
                "overlap_with_prior_zone_count": len(prior_overlaps),
                "nested_with_prior_zone_count": nested_count,
                **lifecycle,
                "entry_trigger_eligible": True,
                "bar_id": anchor["bar_id"],
                "source_bar_ids": json.dumps(
                    [candidate["bar_id"], anchor["bar_id"]],
                    separators=(",", ":"),
                ),
                "definition_version": (
                    f"ob-lookback{lookback}-{geometry}-age{maximum_age}"
                ),
            }
        )
    return (
        pd.DataFrame.from_records(records),
        pd.DataFrame.from_records(diagnostics),
    )
