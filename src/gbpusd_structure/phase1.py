"""Phase-1 cost-aware nested price baselines."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from gbpusd_structure.config import ProjectConfig, load_project_config
from gbpusd_structure.data import canonical_m5_paths, load_canonical_m5
from gbpusd_structure.phase0 import _fingerprint, _prepare_bars, _primary_labels

MODEL_IDS = (
    "p0_session_drift",
    "p1_h4_momentum",
    "p2_h4_sr",
    "p3_m15_structure",
    "p4_top_down_structure",
    "p5_top_down_structure_fvg",
)


@dataclass(frozen=True)
class Phase1Result:
    artifact_directory: Path
    summary: dict[str, Any]


def _utc_timestamp(day: Any, clock: Any, timezone: str) -> pd.Timestamp:
    local = datetime.combine(day, clock, tzinfo=ZoneInfo(timezone))
    return pd.Timestamp(local.astimezone(UTC))


def build_session_opportunities(
    m5: pd.DataFrame,
    config: ProjectConfig,
) -> pd.DataFrame:
    """Build the common London/New York session-day opportunity calendar."""

    timestamps = pd.to_datetime(m5["timestamp"], utc=True)
    records: list[dict[str, Any]] = []
    minutes = config.phase1.opportunity.signal_observation_minutes
    for session_name in config.phase1.scope.sessions:
        session = config.sessions.sessions[session_name]
        local = timestamps.dt.tz_convert(session.timezone)
        mask = (
            local.dt.dayofweek.lt(5)
            & local.dt.hour.eq(session.open.hour)
            & local.dt.minute.eq(session.open.minute)
        )
        for index in np.flatnonzero(mask.to_numpy()):
            session_open = timestamps.iloc[index]
            session_date = local.iloc[index].date()
            if session_name == "london":
                new_york = config.sessions.sessions["new_york"]
                cutoff = _utc_timestamp(
                    session_date,
                    new_york.open,
                    new_york.timezone,
                )
            else:
                cutoff = _utc_timestamp(
                    session_date,
                    config.research.timeframes.fx_day_boundary,
                    config.research.timeframes.fx_day_boundary_timezone,
                )
            if cutoff <= session_open:
                continue
            period = (
                "construction"
                if session_date.year == config.phase1.scope.construction_year
                else "replication"
                if session_date.year == config.phase1.scope.replication_year
                else "outside_scope"
            )
            if period == "outside_scope":
                continue
            records.append(
                {
                    "opportunity_id": (
                        f"{session_date.isoformat()}:{session_name}"
                    ),
                    "session": session_name,
                    "session_date": session_date.isoformat(),
                    "year": session_date.year,
                    "period": period,
                    "session_open_at": session_open,
                    "observation_end_at": session_open
                    + pd.Timedelta(minutes, unit="min"),
                    "cutoff_at": cutoff,
                }
            )
    opportunities = pd.DataFrame.from_records(records)
    if opportunities.empty:
        raise ValueError("Phase 1 opportunity calendar is empty")
    return opportunities.sort_values(
        ["session_open_at", "session"], kind="stable"
    ).reset_index(drop=True)


def build_full_session_opportunities(
    m5: pd.DataFrame,
    config: ProjectConfig,
) -> pd.DataFrame:
    """Use the complete registered session as the setup observation window."""

    opportunities = build_session_opportunities(m5, config)
    opportunities["observation_end_at"] = opportunities["cutoff_at"]
    return opportunities


def _latest_position(times: pd.Series, at: pd.Timestamp) -> int | None:
    values = pd.to_datetime(times, utc=True).astype("int64").to_numpy()
    position = int(np.searchsorted(values, at.value, side="right") - 1)
    return position if position >= 0 else None


def _latest_state(
    contexts: pd.DataFrame,
    at: pd.Timestamp,
) -> str:
    if contexts.empty:
        return "undetermined"
    ordered = contexts.sort_values("available_at", kind="stable")
    position = _latest_position(ordered["available_at"], at)
    return "undetermined" if position is None else str(ordered.iloc[position]["state"])


def _latest_atr(
    bars: pd.DataFrame,
    at: pd.Timestamp,
) -> float | None:
    ordered = bars.sort_values("available_at", kind="stable")
    position = _latest_position(ordered["available_at"], at)
    if position is None:
        return None
    value = float(ordered.iloc[position]["atr"])
    return value if np.isfinite(value) and value > 0 else None


def _signal_record(
    opportunity: dict[str, Any],
    *,
    model_id: str,
    decision_at: pd.Timestamp,
    direction: str,
    signal_type: str,
    atr: float,
    event_type: str,
    signal_bar_id: str | None,
    setup_bar_at: pd.Timestamp | None,
    feature_available_at: pd.Timestamp,
    parent_signal_id: str | None = None,
    displacement_qualified: bool = False,
) -> dict[str, Any]:
    signal_id = f"signal:{model_id}:{opportunity['opportunity_id']}"
    return {
        **opportunity,
        "signal_id": signal_id,
        "model_id": model_id,
        "decision_at": decision_at,
        "direction": direction,
        "signal_type": signal_type,
        "event_type": event_type,
        "signal_bar_id": signal_bar_id,
        "setup_bar_at": setup_bar_at,
        "feature_available_at": feature_available_at,
        "atr": atr,
        "parent_signal_id": parent_signal_id,
        "displacement_qualified": displacement_qualified,
    }


def _session_open_signals(
    opportunities: pd.DataFrame,
    m15: pd.DataFrame,
    *,
    model_id: str,
    directions: dict[str, str],
    signal_type: str,
) -> pd.DataFrame:
    records = []
    for opportunity in opportunities.to_dict("records"):
        direction = directions.get(opportunity["opportunity_id"])
        if direction is None:
            continue
        decision = opportunity["session_open_at"]
        atr = _latest_atr(m15, decision)
        if atr is None:
            continue
        records.append(
            _signal_record(
                opportunity,
                model_id=model_id,
                decision_at=decision,
                direction=direction,
                signal_type=signal_type,
                atr=atr,
                event_type=signal_type,
                signal_bar_id=None,
                setup_bar_at=None,
                feature_available_at=decision,
            )
        )
    return pd.DataFrame.from_records(records)


def _h4_momentum_directions(
    opportunities: pd.DataFrame,
    h4: pd.DataFrame,
) -> dict[str, str]:
    ordered = h4.sort_values("available_at", kind="stable").reset_index(drop=True)
    directions: dict[str, str] = {}
    for opportunity in opportunities.to_dict("records"):
        position = _latest_position(
            ordered["available_at"], opportunity["session_open_at"]
        )
        if position is None or position < 1:
            continue
        latest = float(ordered.iloc[position]["mid_close"])
        previous = float(ordered.iloc[position - 1]["mid_close"])
        if latest > previous:
            directions[opportunity["opportunity_id"]] = "long"
        elif latest < previous:
            directions[opportunity["opportunity_id"]] = "short"
    return directions


def _m15_structure_signals(
    opportunities: pd.DataFrame,
    events: pd.DataFrame,
) -> pd.DataFrame:
    candidates = _m15_structure_candidates(
        opportunities,
        events,
        decision_must_be_before_end=False,
    )
    return _select_first_structure_signal(
        candidates,
        model_id="p3_m15_structure",
        signal_type="m15_structure",
    )


def _m15_structure_candidates(
    opportunities: pd.DataFrame,
    events: pd.DataFrame,
    *,
    decision_must_be_before_end: bool,
) -> pd.DataFrame:
    eligible = events[events["event_type"].isin(["bos", "choch"])].sort_values(
        ["available_at", "event_id"], kind="stable"
    )
    records = []
    for opportunity in opportunities.to_dict("records"):
        in_window = eligible["event_at"].ge(opportunity["session_open_at"])
        if decision_must_be_before_end:
            in_window &= eligible["available_at"].lt(
                opportunity["observation_end_at"]
            )
        else:
            in_window &= eligible["available_at"].le(
                opportunity["observation_end_at"]
            )
        for event in eligible[in_window].to_dict("records"):
            direction = "long" if event["direction"] == "up" else "short"
            record = _signal_record(
                    opportunity,
                    model_id="p3_m15_structure",
                    decision_at=event["available_at"],
                    direction=direction,
                    signal_type="m15_structure_candidate",
                    atr=float(event["atr"]),
                    event_type=str(event["event_type"]),
                    signal_bar_id=str(event["bar_id"]),
                    setup_bar_at=event["event_at"],
                    feature_available_at=event["available_at"],
                    displacement_qualified=bool(event["displacement_qualified"]),
                )
            record["source_event_id"] = str(event["event_id"])
            record["signal_id"] = (
                f"candidate:p3:{opportunity['opportunity_id']}:"
                f"{event['event_id']}"
            )
            records.append(record)
    return pd.DataFrame.from_records(records)


def _select_first_structure_signal(
    candidates: pd.DataFrame,
    *,
    model_id: str,
    signal_type: str,
) -> pd.DataFrame:
    if candidates.empty:
        output = candidates.copy()
        output["model_id"] = model_id
        output["signal_type"] = signal_type
        return output
    selected = (
        candidates.sort_values(
            ["decision_at", "source_event_id"], kind="stable"
        )
        .groupby("opportunity_id", sort=False, as_index=False)
        .head(1)
        .copy()
    )
    selected["model_id"] = model_id
    selected["signal_type"] = signal_type
    selected["signal_id"] = selected["opportunity_id"].map(
        lambda value: f"signal:{model_id}:{value}"
    )
    return selected.reset_index(drop=True)


def _h4_sr_signals(
    opportunities: pd.DataFrame,
    m15: pd.DataFrame,
    h4: pd.DataFrame,
    zone_snapshots: pd.DataFrame,
    config: ProjectConfig,
    *,
    decision_must_be_before_end: bool = False,
) -> pd.DataFrame:
    bars = m15.sort_values("timestamp", kind="stable").copy()
    bars["previous_mid_close"] = bars["mid_close"].shift(1)
    bars["previous_available_at"] = bars["available_at"].shift(1)
    candidate_bars: list[dict[str, Any]] = []
    for opportunity in opportunities.to_dict("records"):
        in_window = bars["timestamp"].ge(opportunity["session_open_at"])
        if decision_must_be_before_end:
            in_window &= bars["available_at"].lt(
                opportunity["observation_end_at"]
            )
        else:
            in_window &= bars["available_at"].le(
                opportunity["observation_end_at"]
            )
        selected = bars[in_window]
        for row in selected.to_dict("records"):
            candidate_bars.append({**row, "_opportunity": opportunity})
    candidate_bars.sort(key=lambda row: (row["timestamp"], row["bar_id"]))

    snapshots = zone_snapshots.sort_values(
        ["available_at", "zone_id"], kind="stable"
    ).to_dict("records")
    h4_available = (
        pd.to_datetime(h4.sort_values("available_at")["available_at"], utc=True)
        .astype("int64")
        .to_numpy()
    )
    pointer = 0
    active_zones: dict[str, dict[str, Any]] = {}
    completed_opportunities: set[str] = set()
    records = []
    settings = config.phase1.support_resistance_signal

    for bar in candidate_bars:
        while pointer < len(snapshots) and (
            snapshots[pointer]["available_at"] <= bar["timestamp"]
        ):
            snapshot = snapshots[pointer]
            if bool(snapshot["active"]):
                touch_index = int(
                    np.searchsorted(
                        h4_available,
                        pd.Timestamp(snapshot["available_at"]).value,
                        side="right",
                    )
                    - 1
                )
                active_zones[str(snapshot["zone_id"])] = {
                    **snapshot,
                    "_touch_h4_index": touch_index,
                }
            pointer += 1

        opportunity = bar["_opportunity"]
        opportunity_id = opportunity["opportunity_id"]
        if opportunity_id in completed_opportunities:
            continue
        if bar["previous_available_at"] != bar["timestamp"]:
            continue
        atr = float(bar["atr"])
        if not np.isfinite(atr) or atr <= 0:
            continue
        current_h4_index = int(
            np.searchsorted(
                h4_available, pd.Timestamp(bar["timestamp"]).value, side="right"
            )
            - 1
        )
        buffer = settings.breakout_close_buffer_atr * atr
        previous_close = float(bar["previous_mid_close"])
        choices: list[tuple[float, int, str, str, dict[str, Any]]] = []
        for zone_id, zone in active_zones.items():
            age = current_h4_index - int(zone["_touch_h4_index"])
            if age < 0 or age > settings.maximum_zone_age_h4_bars:
                continue
            lower = float(zone["lower_bound"])
            upper = float(zone["upper_bound"])
            center = float(zone["center"])
            intersects = float(bar["mid_low"]) <= upper and float(
                bar["mid_high"]
            ) >= lower
            events: list[tuple[str, str, int]] = []
            if zone["role"] == "resistance":
                if previous_close <= upper + buffer and float(
                    bar["mid_close"]
                ) > upper + buffer:
                    events.append(("long", "resistance_breakout", 0))
                if (
                    previous_close < lower
                    and intersects
                    and float(bar["mid_close"]) < lower
                ):
                    events.append(("short", "resistance_rejection", 1))
            else:
                if previous_close >= lower - buffer and float(
                    bar["mid_close"]
                ) < lower - buffer:
                    events.append(("short", "support_breakout", 0))
                if (
                    previous_close > upper
                    and intersects
                    and float(bar["mid_close"]) > upper
                ):
                    events.append(("long", "support_rejection", 1))
            distance = abs(previous_close - center) / atr
            for direction, event_type, event_order in events:
                choices.append(
                    (
                        distance,
                        event_order,
                        zone_id,
                        direction,
                        {**zone, "_event": event_type},
                    )
                )
        if not choices:
            continue
        _, _, zone_id, direction, zone = min(choices, key=lambda item: item[:3])
        records.append(
            {
                **_signal_record(
                    opportunity,
                    model_id="p2_h4_sr",
                    decision_at=bar["available_at"],
                    direction=direction,
                    signal_type="h4_sr_interaction",
                    atr=atr,
                    event_type=str(zone["_event"]),
                    signal_bar_id=str(bar["bar_id"]),
                    setup_bar_at=bar["timestamp"],
                    feature_available_at=zone["available_at"],
                ),
                "zone_id": zone_id,
                "zone_role": zone["role"],
                "zone_lower_bound": zone["lower_bound"],
                "zone_upper_bound": zone["upper_bound"],
            }
        )
        completed_opportunities.add(opportunity_id)
    return pd.DataFrame.from_records(records)


def _attach_contexts(
    signals: pd.DataFrame,
    contexts: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    if signals.empty:
        return signals.copy()
    output = signals.copy()
    for timeframe, column in (
        ("1H", "h1_context"),
        ("4H", "h4_context"),
        ("1D", "daily_context"),
    ):
        output[column] = [
            _latest_state(contexts[timeframe], timestamp)
            for timestamp in output["decision_at"]
        ]
    return output


def _top_down_signals(
    p3: pd.DataFrame,
    fvg: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if p3.empty:
        return pd.DataFrame(), pd.DataFrame()
    desired = p3["direction"].map({"long": "bullish", "short": "bearish"})
    aligned = p3[p3["h1_context"].eq(desired) & p3["h4_context"].eq(desired)].copy()
    aligned["model_id"] = "p4_top_down_structure"
    aligned["parent_signal_id"] = aligned["signal_id"]
    aligned["signal_id"] = aligned["opportunity_id"].map(
        lambda value: f"signal:p4_top_down_structure:{value}"
    )
    aligned["signal_type"] = "top_down_m15_structure"

    fvg_keys = set(
        fvg[["bar_id", "direction"]]
        .assign(
            direction=lambda frame: frame["direction"].map(
                {"up": "long", "down": "short"}
            )
        )
        [["bar_id", "direction"]]
        .itertuples(index=False, name=None)
    )
    keep = [
        bool(row["displacement_qualified"])
        and (row["signal_bar_id"], row["direction"]) in fvg_keys
        for row in aligned.to_dict("records")
    ]
    with_fvg = aligned[np.asarray(keep, dtype=bool)].copy()
    with_fvg["model_id"] = "p5_top_down_structure_fvg"
    with_fvg["parent_signal_id"] = with_fvg["signal_id"]
    with_fvg["signal_id"] = with_fvg["opportunity_id"].map(
        lambda value: f"signal:p5_top_down_structure_fvg:{value}"
    )
    with_fvg["signal_type"] = "top_down_structure_displacement_fvg"
    return aligned, with_fvg


def _full_session_structure_signals(
    opportunities: pd.DataFrame,
    events: pd.DataFrame,
    contexts: dict[str, pd.DataFrame],
    fvg: pd.DataFrame,
) -> tuple[
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
]:
    candidates = _m15_structure_candidates(
        opportunities,
        events,
        decision_must_be_before_end=True,
    )
    candidates = _attach_contexts(candidates, contexts)
    p3 = _select_first_structure_signal(
        candidates,
        model_id="p3_m15_structure",
        signal_type="first_full_session_m15_structure",
    )

    desired = candidates["direction"].map(
        {"long": "bullish", "short": "bearish"}
    )
    aligned_candidates = candidates[
        candidates["h1_context"].eq(desired)
        & candidates["h4_context"].eq(desired)
    ].copy()
    p4 = _select_first_structure_signal(
        aligned_candidates,
        model_id="p4_top_down_structure",
        signal_type="first_full_session_top_down_structure",
    )
    p4["parent_candidate_id"] = p4["source_event_id"].map(
        lambda value: f"candidate:p3:{value}"
    )

    fvg_keys = set(
        fvg[["bar_id", "direction"]]
        .assign(
            direction=lambda frame: frame["direction"].map(
                {"up": "long", "down": "short"}
            )
        )
        [["bar_id", "direction"]]
        .itertuples(index=False, name=None)
    )
    fvg_mask = [
        bool(row["displacement_qualified"])
        and (row["signal_bar_id"], row["direction"]) in fvg_keys
        for row in aligned_candidates.to_dict("records")
    ]
    fvg_candidates = aligned_candidates[np.asarray(fvg_mask, dtype=bool)].copy()
    p5 = _select_first_structure_signal(
        fvg_candidates,
        model_id="p5_top_down_structure_fvg",
        signal_type="first_full_session_top_down_displacement_fvg",
    )
    p5["parent_candidate_id"] = p5["source_event_id"].map(
        lambda value: f"candidate:p4:{value}"
    )
    return p3, p4, p5, candidates, aligned_candidates, fvg_candidates


def _attach_local_decision_hour(
    signals: pd.DataFrame,
    config: ProjectConfig,
) -> pd.DataFrame:
    output = signals.copy()
    hours = []
    for row in output.to_dict("records"):
        timezone = config.sessions.sessions[row["session"]].timezone
        local = pd.Timestamp(row["decision_at"]).tz_convert(timezone)
        hours.append(f"{local.hour:02d}:00")
    output["decision_local_hour"] = hours
    return output


def _simulate_trade(
    signal: dict[str, Any],
    m5: pd.DataFrame,
    config: ProjectConfig,
    *,
    slippage_pips_per_side: float,
) -> dict[str, Any] | None:
    """Simulate one signal on executable-side M5 quotes."""

    timestamps = pd.to_datetime(m5["timestamp"], utc=True)
    entry_position = int(
        np.searchsorted(
            timestamps.astype("int64").to_numpy(),
            pd.Timestamp(signal["decision_at"]).value,
            side="left",
        )
    )
    cutoff_position = int(
        np.searchsorted(
            timestamps.astype("int64").to_numpy(),
            pd.Timestamp(signal["cutoff_at"]).value,
            side="left",
        )
    )
    if entry_position >= len(m5) or entry_position >= cutoff_position:
        return None
    entry_bar = m5.iloc[entry_position]
    entry_at = pd.Timestamp(entry_bar["timestamp"])
    if entry_at < signal["decision_at"] or entry_at >= signal["cutoff_at"]:
        return None
    atr = float(signal["atr"])
    if not np.isfinite(atr) or atr <= 0:
        return None
    pip_size = config.research.instrument.pip_size
    stop_distance = config.phase1.risk.stop_atr * atr
    target_distance = config.phase1.risk.target_r * stop_distance
    direction = signal["direction"]
    if direction == "long":
        reference_entry = float(entry_bar["ask_open"])
        stop = reference_entry - stop_distance
        target = reference_entry + target_distance
    else:
        reference_entry = float(entry_bar["bid_open"])
        stop = reference_entry + stop_distance
        target = reference_entry - target_distance

    raw_exit = None
    exit_at = None
    exit_reason = None
    for position in range(entry_position, cutoff_position):
        bar = m5.iloc[position]
        if direction == "long":
            quote_open = float(bar["bid_open"])
            stop_touch = float(bar["bid_low"]) <= stop
            target_touch = float(bar["bid_high"]) >= target
            if quote_open <= stop:
                raw_exit, exit_reason = quote_open, "stop_gap"
            elif quote_open >= target:
                raw_exit, exit_reason = target, "target_gap"
            elif stop_touch:
                raw_exit, exit_reason = stop, "stop"
            elif target_touch:
                raw_exit, exit_reason = target, "target"
        else:
            quote_open = float(bar["ask_open"])
            stop_touch = float(bar["ask_high"]) >= stop
            target_touch = float(bar["ask_low"]) <= target
            if quote_open >= stop:
                raw_exit, exit_reason = quote_open, "stop_gap"
            elif quote_open <= target:
                raw_exit, exit_reason = target, "target_gap"
            elif stop_touch:
                raw_exit, exit_reason = stop, "stop"
            elif target_touch:
                raw_exit, exit_reason = target, "target"
        if raw_exit is not None:
            exit_at = pd.Timestamp(bar["timestamp"]) + pd.Timedelta(5, unit="min")
            break

    if raw_exit is None:
        final_bar = m5.iloc[cutoff_position - 1]
        raw_exit = float(
            final_bar["bid_close"]
            if direction == "long"
            else final_bar["ask_close"]
        )
        exit_at = min(
            pd.Timestamp(final_bar["timestamp"]) + pd.Timedelta(5, unit="min"),
            pd.Timestamp(signal["cutoff_at"]),
        )
        exit_reason = "time"

    slip = slippage_pips_per_side * pip_size
    if direction == "long":
        entry_fill = reference_entry + slip
        exit_fill = float(raw_exit) - slip
        pnl_pips_before_commission = (exit_fill - entry_fill) / pip_size
    else:
        entry_fill = reference_entry - slip
        exit_fill = float(raw_exit) + slip
        pnl_pips_before_commission = (entry_fill - exit_fill) / pip_size
    commission_pips = 2 * config.execution.costs.commission_pips_per_side
    net_pips = pnl_pips_before_commission - commission_pips
    risk_pips = stop_distance / pip_size
    return {
        **signal,
        "trade_id": f"trade:{signal['model_id']}:{signal['opportunity_id']}",
        "entry_at": entry_at,
        "exit_at": exit_at,
        "entry_reference_price": reference_entry,
        "entry_fill_price": entry_fill,
        "exit_fill_price": exit_fill,
        "stop_price": stop,
        "target_price": target,
        "exit_reason": exit_reason,
        "risk_pips": risk_pips,
        "slippage_pips_per_side": slippage_pips_per_side,
        "commission_pips_round_trip": commission_pips,
        "net_pips": net_pips,
        "net_r": net_pips / risk_pips,
        "win": net_pips > 0,
    }


def _simulate_signals(
    signals: pd.DataFrame,
    m5: pd.DataFrame,
    config: ProjectConfig,
    *,
    slippage_pips_per_side: float,
) -> pd.DataFrame:
    records = [
        trade
        for signal in signals.to_dict("records")
        if (
            trade := _simulate_trade(
                signal,
                m5,
                config,
                slippage_pips_per_side=slippage_pips_per_side,
            )
        )
        is not None
    ]
    return pd.DataFrame.from_records(records)


def _fit_p0_directions(
    opportunities: pd.DataFrame,
    m15: pd.DataFrame,
    m5: pd.DataFrame,
    config: ProjectConfig,
) -> tuple[dict[str, str], pd.DataFrame]:
    construction = opportunities[opportunities["period"].eq("construction")]
    candidates = []
    for direction in config.phase1.session_drift_fit.candidates:
        directions = dict.fromkeys(construction["opportunity_id"], direction)
        signals = _session_open_signals(
            construction,
            m15,
            model_id=f"p0_fit_{direction}",
            directions=directions,
            signal_type="session_drift_fit",
        )
        trades = _simulate_signals(
            signals,
            m5,
            config,
            slippage_pips_per_side=config.execution.costs.slippage_pips_per_side,
        )
        candidates.append(trades)
    fitted = pd.concat(candidates, ignore_index=True)
    rows = []
    selected: dict[str, str] = {}
    for session in config.phase1.scope.sessions:
        scoped = fitted[fitted["session"].eq(session)]
        means = {
            direction: float(
                scoped[scoped["direction"].eq(direction)]["net_r"].mean()
            )
            for direction in config.phase1.session_drift_fit.candidates
        }
        chosen = (
            "long"
            if means["long"] >= means["short"]
            else "short"
        )
        selected[session] = chosen
        for direction, mean in means.items():
            rows.append(
                {
                    "session": session,
                    "direction": direction,
                    "construction_mean_net_r": mean,
                    "selected": direction == chosen,
                }
            )
    directions = {
        row["opportunity_id"]: selected[row["session"]]
        for row in opportunities.to_dict("records")
    }
    return directions, pd.DataFrame.from_records(rows)


def _opportunity_panel(
    opportunities: pd.DataFrame,
    trades: pd.DataFrame,
) -> pd.DataFrame:
    model_frame = pd.DataFrame({"model_id": MODEL_IDS})
    panel = opportunities.merge(model_frame, how="cross")
    values = trades[["opportunity_id", "model_id", "net_r"]].rename(
        columns={"net_r": "trade_net_r"}
    )
    panel = panel.merge(values, on=["opportunity_id", "model_id"], how="left")
    panel["traded"] = panel["trade_net_r"].notna()
    panel["net_r"] = panel["trade_net_r"].fillna(0.0)
    return panel.drop(columns=["trade_net_r"])


def _profit_factor(values: pd.Series) -> float | None:
    positive = float(values[values.gt(0)].sum())
    negative = abs(float(values[values.lt(0)].sum()))
    return positive / negative if negative > 0 else None


def _metric_record(
    frame: pd.DataFrame,
    opportunities: pd.DataFrame,
    *,
    model_id: str,
    period: str,
    scope: str,
    value: str,
) -> dict[str, Any]:
    net = frame["net_r"] if not frame.empty else pd.Series(dtype="float64")
    return {
        "model_id": model_id,
        "period": period,
        "scope": scope,
        "value": value,
        "opportunity_count": len(opportunities),
        "trade_count": len(frame),
        "participation_rate": (
            len(frame) / len(opportunities) if len(opportunities) else None
        ),
        "total_net_r": float(net.sum()),
        "mean_trade_net_r": float(net.mean()) if len(net) else None,
        "median_trade_net_r": float(net.median()) if len(net) else None,
        "win_rate": float(frame["win"].mean()) if len(frame) else None,
        "profit_factor": _profit_factor(net),
        "mean_opportunity_net_r": (
            float(net.sum()) / len(opportunities) if len(opportunities) else None
        ),
    }


def _metrics(
    opportunities: pd.DataFrame,
    trades: pd.DataFrame,
) -> pd.DataFrame:
    records = []
    for model_id in MODEL_IDS:
        model_trades = trades[trades["model_id"].eq(model_id)]
        for period in ("construction", "replication"):
            period_opportunities = opportunities[opportunities["period"].eq(period)]
            period_trades = model_trades[model_trades["period"].eq(period)]
            records.append(
                _metric_record(
                    period_trades,
                    period_opportunities,
                    model_id=model_id,
                    period=period,
                    scope="overall",
                    value="all",
                )
            )
            for session in ("london", "new_york"):
                records.append(
                    _metric_record(
                        period_trades[period_trades["session"].eq(session)],
                        period_opportunities[
                            period_opportunities["session"].eq(session)
                        ],
                        model_id=model_id,
                        period=period,
                        scope="session",
                        value=session,
                    )
                )
            for direction in ("long", "short"):
                direction_trades = period_trades[
                    period_trades["direction"].eq(direction)
                ]
                records.append(
                    _metric_record(
                        direction_trades,
                        period_opportunities,
                        model_id=model_id,
                        period=period,
                        scope="direction",
                        value=direction,
                    )
                )
            for column, scope in (
                ("daily_context", "daily_context"),
                ("event_type", "event_type"),
                ("exit_reason", "exit_reason"),
            ):
                for value in sorted(period_trades[column].dropna().unique()):
                    records.append(
                        _metric_record(
                            period_trades[period_trades[column].eq(value)],
                            period_opportunities,
                            model_id=model_id,
                            period=period,
                            scope=scope,
                            value=str(value),
                        )
                    )
    return pd.DataFrame.from_records(records)


def _cluster_bootstrap(
    panel: pd.DataFrame,
    config: ProjectConfig,
) -> pd.DataFrame:
    replication = panel[panel["period"].eq("replication")]
    rng = np.random.default_rng(config.research.study.random_seed)
    resamples = config.phase1.statistics.bootstrap_resamples
    alpha = 1 - config.phase1.statistics.confidence_level
    rows = []
    for model_id in MODEL_IDS:
        scoped = replication[replication["model_id"].eq(model_id)]
        daily = scoped.groupby("session_date", sort=True)["net_r"].agg(
            ["sum", "count"]
        )
        positions = rng.integers(0, len(daily), size=(resamples, len(daily)))
        sampled_sum = daily["sum"].to_numpy()[positions].sum(axis=1)
        sampled_count = daily["count"].to_numpy()[positions].sum(axis=1)
        estimates = sampled_sum / sampled_count
        rows.append(
            {
                "model_id": model_id,
                "comparison": "mean_opportunity_net_r",
                "estimate": float(scoped["net_r"].mean()),
                "ci_lower": float(np.quantile(estimates, alpha / 2)),
                "ci_upper": float(np.quantile(estimates, 1 - alpha / 2)),
            }
        )
    for candidate, parent in config.phase1.advancement_gate.nearest_baseline.items():
        pivot = replication.pivot(
            index=["session_date", "session"],
            columns="model_id",
            values="net_r",
        )
        difference = (pivot[candidate] - pivot[parent]).rename("difference")
        daily = difference.groupby(level="session_date").agg(["sum", "count"])
        positions = rng.integers(0, len(daily), size=(resamples, len(daily)))
        estimates = (
            daily["sum"].to_numpy()[positions].sum(axis=1)
            / daily["count"].to_numpy()[positions].sum(axis=1)
        )
        rows.append(
            {
                "model_id": candidate,
                "comparison": f"incremental_vs_{parent}",
                "estimate": float(difference.mean()),
                "ci_lower": float(np.quantile(estimates, alpha / 2)),
                "ci_upper": float(np.quantile(estimates, 1 - alpha / 2)),
            }
        )
    return pd.DataFrame.from_records(rows)


def _invariant_failures(
    signals: pd.DataFrame,
    trades: pd.DataFrame,
    *,
    require_selected_parent_subset: bool = True,
) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []

    def check(name: str, mask: pd.Series) -> None:
        count = int(mask.sum())
        if count:
            failures.append({"invariant": name, "failure_count": count})

    check(
        "feature_available_by_decision",
        signals["feature_available_at"].gt(signals["decision_at"]),
    )
    check(
        "decision_not_before_session",
        signals["decision_at"].lt(signals["session_open_at"]),
    )
    check(
        "decision_within_observation",
        signals["decision_at"].gt(signals["observation_end_at"]),
    )
    check("entry_not_before_decision", trades["entry_at"].lt(trades["decision_at"]))
    check("entry_before_cutoff", trades["entry_at"].ge(trades["cutoff_at"]))
    check("exit_by_cutoff", trades["exit_at"].gt(trades["cutoff_at"]))
    duplicates = trades.duplicated(["model_id", "opportunity_id"], keep=False)
    check("one_trade_per_model_session", duplicates)
    if require_selected_parent_subset:
        for child, parent in (
            ("p4_top_down_structure", "p3_m15_structure"),
            ("p5_top_down_structure_fvg", "p4_top_down_structure"),
        ):
            child_keys = set(
                signals[signals["model_id"].eq(child)][
                    ["opportunity_id", "direction"]
                ].itertuples(index=False, name=None)
            )
            parent_keys = set(
                signals[signals["model_id"].eq(parent)][
                    ["opportunity_id", "direction"]
                ].itertuples(index=False, name=None)
            )
            missing = len(child_keys.difference(parent_keys))
            if missing:
                failures.append(
                    {
                        "invariant": f"{child}_subset_of_{parent}",
                        "failure_count": missing,
                    }
                )
    forbidden = [
        column
        for column in signals.columns
        if "order_block" in column or "h1_sr" in column
    ]
    if forbidden:
        failures.append(
            {"invariant": "forbidden_feature_columns", "columns": forbidden}
        )
    return failures


def _monthly_concentration(trades: pd.DataFrame, model_id: str) -> float | None:
    scoped = trades[
        trades["model_id"].eq(model_id) & trades["period"].eq("replication")
    ].copy()
    if scoped.empty:
        return None
    scoped["month"] = (
        pd.to_datetime(scoped["session_date"]).dt.to_period("M").astype(str)
    )
    monthly = scoped.groupby("month")["net_r"].sum()
    positive = monthly[monthly.gt(0)]
    return float(positive.max() / positive.sum()) if len(positive) else None


def _candidate_gates(
    opportunities: pd.DataFrame,
    trades: pd.DataFrame,
    stress_trades: pd.DataFrame,
    panel: pd.DataFrame,
    bootstrap: pd.DataFrame,
    failures: list[dict[str, Any]],
    config: ProjectConfig,
) -> dict[str, Any]:
    settings = config.phase1.advancement_gate
    output: dict[str, Any] = {}
    for candidate in settings.candidates:
        scoped = trades[trades["model_id"].eq(candidate)]
        construction = scoped[scoped["period"].eq("construction")]
        replication = scoped[scoped["period"].eq("replication")]
        stress_replication = stress_trades[
            stress_trades["model_id"].eq(candidate)
            & stress_trades["period"].eq("replication")
        ]
        parent = settings.nearest_baseline[candidate]
        replication_panel = panel[panel["period"].eq("replication")]
        means = replication_panel.groupby("model_id")["net_r"].mean()
        ci_row = bootstrap[
            bootstrap["model_id"].eq(candidate)
            & bootstrap["comparison"].eq("mean_opportunity_net_r")
        ].iloc[0]
        concentration = _monthly_concentration(trades, candidate)
        checks = {
            "zero_causality_failures": not failures,
            "minimum_trades_each_year": all(
                len(scoped[scoped["year"].eq(year)])
                >= settings.minimum_trades_per_year
                for year in (2024, 2025)
            ),
            "minimum_replication_trades_each_session": all(
                len(replication[replication["session"].eq(session)])
                >= settings.minimum_trades_per_session_replication
                for session in ("london", "new_york")
            ),
            "minimum_replication_trades_each_direction": all(
                len(replication[replication["direction"].eq(direction)])
                >= settings.minimum_trades_per_direction_replication
                for direction in ("long", "short")
            ),
            "positive_construction_expectancy": bool(
                len(construction) and construction["net_r"].mean() > 0
            ),
            "positive_replication_expectancy": bool(
                len(replication) and replication["net_r"].mean() > 0
            ),
            "positive_replication_each_session": all(
                len(part := replication[replication["session"].eq(session)])
                and part["net_r"].mean() > 0
                for session in ("london", "new_york")
            ),
            "positive_replication_each_direction": all(
                len(part := replication[replication["direction"].eq(direction)])
                and part["net_r"].mean() > 0
                for direction in ("long", "short")
            ),
            "replication_profit_factor_above_one": bool(
                (_profit_factor(replication["net_r"]) or 0) > 1
            ),
            "replication_opportunity_ci_above_zero": bool(ci_row["ci_lower"] > 0),
            "positive_stress_replication_expectancy": bool(
                len(stress_replication) and stress_replication["net_r"].mean() > 0
            ),
            "monthly_concentration": bool(
                concentration is not None
                and concentration <= settings.maximum_best_month_share_of_positive_r
            ),
            "positive_increment_vs_parent": bool(means[candidate] > means[parent]),
        }
        output[candidate] = {
            "passed": all(checks.values()),
            "checks": checks,
            "trade_counts": {
                "construction": len(construction),
                "replication": len(replication),
            },
            "replication_mean_trade_net_r": (
                float(replication["net_r"].mean()) if len(replication) else None
            ),
            "stress_replication_mean_trade_net_r": (
                float(stress_replication["net_r"].mean())
                if len(stress_replication)
                else None
            ),
            "replication_mean_opportunity_net_r": float(means[candidate]),
            "parent_mean_opportunity_net_r": float(means[parent]),
            "replication_opportunity_ci": [
                float(ci_row["ci_lower"]),
                float(ci_row["ci_upper"]),
            ],
            "best_month_share_of_positive_r": concentration,
        }
    return output


def _json_default(value: Any) -> Any:
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    if isinstance(value, np.generic):
        return value.item()
    if pd.isna(value):
        return None
    raise TypeError(f"Not JSON serializable: {type(value)!r}")


def _validate_phase11_shared_settings(config: ProjectConfig) -> None:
    original = config.phase1
    revision = config.phase1_1
    pairs = (
        (original.scope, revision.scope),
        (original.session_drift_fit, revision.session_drift_fit),
        (original.support_resistance_signal, revision.support_resistance_signal),
        (original.structure_signal, revision.structure_signal),
        (original.risk, revision.risk),
        (original.statistics, revision.statistics),
        (original.advancement_gate, revision.advancement_gate),
    )
    if any(left != right for left, right in pairs):
        raise ValueError(
            "Phase 1.1 may change only the setup window and per-model selection"
        )
    original_ids = tuple(item.id for item in original.baselines)
    revision_ids = tuple(item.id for item in revision.baselines)
    if original_ids != revision_ids:
        raise ValueError("Phase 1.1 model IDs must match Phase 1")


def _selected_signal_keys(frame: pd.DataFrame, model_id: str) -> set[tuple[Any, ...]]:
    scoped = frame[frame["model_id"].eq(model_id)]
    return set(
        scoped[
            ["opportunity_id", "direction", "decision_at"]
        ].itertuples(index=False, name=None)
    )


def _phase11_invariant_failures(
    signals: pd.DataFrame,
    trades: pd.DataFrame,
    structure_candidates: pd.DataFrame,
    aligned_candidates: pd.DataFrame,
    fvg_candidates: pd.DataFrame,
    parent_signals: pd.DataFrame,
) -> list[dict[str, Any]]:
    failures = _invariant_failures(
        signals,
        trades,
        require_selected_parent_subset=False,
    )

    def add(name: str, count: int) -> None:
        if count:
            failures.append({"invariant": name, "failure_count": int(count)})

    setup_models = {
        "p2_h4_sr",
        "p3_m15_structure",
        "p4_top_down_structure",
        "p5_top_down_structure_fvg",
    }
    setup_signals = signals[signals["model_id"].isin(setup_models)]
    add(
        "full_session_decision_strictly_before_cutoff",
        int(setup_signals["decision_at"].ge(setup_signals["cutoff_at"]).sum()),
    )
    add(
        "setup_not_before_session",
        int(setup_signals["setup_bar_at"].lt(setup_signals["session_open_at"]).sum()),
    )
    add(
        "setup_precedes_decision",
        int(setup_signals["setup_bar_at"].ge(setup_signals["decision_at"]).sum()),
    )

    candidate_ids = set(structure_candidates["source_event_id"])
    aligned_ids = set(aligned_candidates["source_event_id"])
    fvg_ids = set(fvg_candidates["source_event_id"])
    selected_p3 = set(
        signals[signals["model_id"].eq("p3_m15_structure")]["source_event_id"]
    )
    selected_p4 = set(
        signals[signals["model_id"].eq("p4_top_down_structure")][
            "source_event_id"
        ]
    )
    selected_p5 = set(
        signals[signals["model_id"].eq("p5_top_down_structure_fvg")][
            "source_event_id"
        ]
    )
    add("p3_selected_from_structure_candidates", len(selected_p3 - candidate_ids))
    add("p4_selected_from_aligned_candidates", len(selected_p4 - aligned_ids))
    add("p5_selected_from_fvg_candidates", len(selected_p5 - fvg_ids))
    add("aligned_candidates_subset", len(aligned_ids - candidate_ids))
    add("fvg_candidates_subset", len(fvg_ids - aligned_ids))

    for model_id in ("p0_session_drift", "p1_h4_momentum"):
        current = _selected_signal_keys(signals, model_id)
        parent = _selected_signal_keys(parent_signals, model_id)
        add(f"{model_id}_identical_to_parent", len(current ^ parent))
    return failures


def run_phase1(
    project_root: Path,
    data_root: Path,
    *,
    artifact_root: Path | None = None,
) -> Phase1Result:
    """Run the preregistered Phase-1 nested price baselines."""

    config = load_project_config(project_root / "config")
    input_paths = canonical_m5_paths(data_root, config.research)
    fingerprint, input_hashes = _fingerprint(project_root, input_paths)
    parent = artifact_root or project_root / "artifacts" / "phase1"
    output = parent / fingerprint
    output.mkdir(parents=True, exist_ok=True)

    m5 = load_canonical_m5(data_root, config.research)
    bars = _prepare_bars(m5, config)
    (
        _,
        breaks,
        gaps,
        _,
        snapshots,
        contexts,
        _,
        _,
    ) = _primary_labels(bars, config)
    opportunities = build_session_opportunities(m5, config)

    p0_directions, p0_fit = _fit_p0_directions(
        opportunities, bars["15min"], m5, config
    )
    p0 = _session_open_signals(
        opportunities,
        bars["15min"],
        model_id="p0_session_drift",
        directions=p0_directions,
        signal_type="fitted_fixed_session_direction",
    )
    momentum = _h4_momentum_directions(opportunities, bars["4H"])
    p1 = _session_open_signals(
        opportunities,
        bars["15min"],
        model_id="p1_h4_momentum",
        directions=momentum,
        signal_type="latest_completed_h4_close_change",
    )
    p2 = _h4_sr_signals(
        opportunities,
        bars["15min"],
        bars["4H"],
        snapshots["4H"],
        config,
    )
    p3 = _m15_structure_signals(opportunities, breaks["15min"])
    p3 = _attach_contexts(p3, contexts)
    p4, p5 = _top_down_signals(p3, gaps["15min"])

    base = pd.concat(
        [frame.dropna(axis=1, how="all") for frame in (p0, p1, p2)],
        ignore_index=True,
        sort=False,
    )
    base = _attach_contexts(base, contexts)
    signals = pd.concat([base, p3, p4, p5], ignore_index=True, sort=False)
    signals = signals.sort_values(
        ["decision_at", "model_id", "opportunity_id"], kind="stable"
    ).reset_index(drop=True)

    primary_slippage = config.execution.costs.slippage_pips_per_side
    stress_slippage = config.execution.costs.stress_slippage_pips_per_side
    trades = _simulate_signals(
        signals, m5, config, slippage_pips_per_side=primary_slippage
    )
    stress_trades = _simulate_signals(
        signals, m5, config, slippage_pips_per_side=stress_slippage
    )
    panel = _opportunity_panel(opportunities, trades)
    stress_panel = _opportunity_panel(opportunities, stress_trades)
    metrics = _metrics(opportunities, trades)
    stress_metrics = _metrics(opportunities, stress_trades)
    bootstrap = _cluster_bootstrap(panel, config)
    failures = _invariant_failures(signals, trades)
    gates = _candidate_gates(
        opportunities,
        trades,
        stress_trades,
        panel,
        bootstrap,
        failures,
        config,
    )

    summary = {
        "phase": "phase1_nested_price_baselines",
        "fingerprint": fingerprint,
        "price_source": config.research.data.price_source,
        "source_role": config.research.data.source_role,
        "broker_specific_spread_claim": (
            config.execution.pricing.broker_specific_spread_claim
        ),
        "order_block_used": False,
        "h1_support_resistance_used": False,
        "fundamental_used": False,
        "opportunity_count": len(opportunities),
        "signal_counts": {
            model_id: int(signals["model_id"].eq(model_id).sum())
            for model_id in MODEL_IDS
        },
        "p0_selected_directions": {
            row["session"]: row["direction"]
            for row in p0_fit[p0_fit["selected"]].to_dict("records")
        },
        "invariant_failure_count": sum(
            int(item.get("failure_count", 1)) for item in failures
        ),
        "invariant_failures": failures,
        "candidate_gates": gates,
        "any_candidate_passed": any(item["passed"] for item in gates.values()),
    }

    opportunities.to_parquet(output / "opportunities.parquet", index=False)
    signals.to_parquet(output / "signals.parquet", index=False)
    trades.to_parquet(output / "trades-primary.parquet", index=False)
    stress_trades.to_parquet(output / "trades-stress.parquet", index=False)
    panel.to_parquet(output / "opportunity-panel-primary.parquet", index=False)
    stress_panel.to_parquet(output / "opportunity-panel-stress.parquet", index=False)
    p0_fit.to_csv(output / "p0-fit.csv", index=False)
    metrics.to_csv(output / "metrics-primary.csv", index=False)
    stress_metrics.to_csv(output / "metrics-stress.csv", index=False)
    bootstrap.to_csv(output / "bootstrap.csv", index=False)
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True, default=_json_default) + "\n",
        encoding="utf-8",
    )
    manifest = {
        "phase": summary["phase"],
        "fingerprint": fingerprint,
        "created_at": datetime.now(UTC).isoformat(),
        "input_hashes": input_hashes,
        "config_status": config.phase1.status,
        "artifact_files": sorted(path.name for path in output.iterdir()),
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return Phase1Result(artifact_directory=output, summary=summary)


def run_phase1_1(
    project_root: Path,
    data_root: Path,
    *,
    artifact_root: Path | None = None,
) -> Phase1Result:
    """Run the preregistered Phase-1.1 full-session setup revision."""

    config = load_project_config(project_root / "config")
    _validate_phase11_shared_settings(config)
    parent_artifact = (
        project_root
        / "artifacts"
        / "phase1"
        / config.phase1_1.parent.fingerprint
    )
    parent_signal_path = parent_artifact / "signals.parquet"
    if not parent_signal_path.is_file():
        raise ValueError(
            "Phase 1.1 requires the registered parent signals artifact: "
            f"{parent_signal_path}"
        )

    input_paths = canonical_m5_paths(data_root, config.research)
    fingerprint, input_hashes = _fingerprint(project_root, input_paths)
    parent = artifact_root or project_root / "artifacts" / "phase1_1"
    output = parent / fingerprint
    output.mkdir(parents=True, exist_ok=True)

    m5 = load_canonical_m5(data_root, config.research)
    bars = _prepare_bars(m5, config)
    (
        _,
        breaks,
        gaps,
        _,
        snapshots,
        contexts,
        _,
        _,
    ) = _primary_labels(bars, config)
    opportunities = build_full_session_opportunities(m5, config)

    p0_directions, p0_fit = _fit_p0_directions(
        opportunities, bars["15min"], m5, config
    )
    p0 = _session_open_signals(
        opportunities,
        bars["15min"],
        model_id="p0_session_drift",
        directions=p0_directions,
        signal_type="fitted_fixed_session_direction",
    )
    momentum = _h4_momentum_directions(opportunities, bars["4H"])
    p1 = _session_open_signals(
        opportunities,
        bars["15min"],
        model_id="p1_h4_momentum",
        directions=momentum,
        signal_type="latest_completed_h4_close_change",
    )
    p2 = _h4_sr_signals(
        opportunities,
        bars["15min"],
        bars["4H"],
        snapshots["4H"],
        config,
        decision_must_be_before_end=True,
    )
    (
        p3,
        p4,
        p5,
        structure_candidates,
        aligned_candidates,
        fvg_candidates,
    ) = _full_session_structure_signals(
        opportunities,
        breaks["15min"],
        contexts,
        gaps["15min"],
    )

    base = pd.concat(
        [frame.dropna(axis=1, how="all") for frame in (p0, p1, p2)],
        ignore_index=True,
        sort=False,
    )
    base = _attach_contexts(base, contexts)
    signals = pd.concat([base, p3, p4, p5], ignore_index=True, sort=False)
    signals = signals.sort_values(
        ["decision_at", "model_id", "opportunity_id"], kind="stable"
    ).reset_index(drop=True)
    signals = _attach_local_decision_hour(signals, config)

    primary_slippage = config.execution.costs.slippage_pips_per_side
    stress_slippage = config.execution.costs.stress_slippage_pips_per_side
    trades = _simulate_signals(
        signals, m5, config, slippage_pips_per_side=primary_slippage
    )
    stress_trades = _simulate_signals(
        signals, m5, config, slippage_pips_per_side=stress_slippage
    )
    panel = _opportunity_panel(opportunities, trades)
    stress_panel = _opportunity_panel(opportunities, stress_trades)
    metrics = _metrics(opportunities, trades)
    stress_metrics = _metrics(opportunities, stress_trades)
    bootstrap = _cluster_bootstrap(panel, config)

    parent_signals = pd.read_parquet(parent_signal_path)
    failures = _phase11_invariant_failures(
        signals,
        trades,
        structure_candidates,
        aligned_candidates,
        fvg_candidates,
        parent_signals,
    )
    gates = _candidate_gates(
        opportunities,
        trades,
        stress_trades,
        panel,
        bootstrap,
        failures,
        config,
    )

    desired = structure_candidates["direction"].map(
        {"long": "bullish", "short": "bearish"}
    )
    h1_aligned = structure_candidates["h1_context"].eq(desired)
    h4_aligned = structure_candidates["h4_context"].eq(desired)
    alignment_funnel = {
        "structure_candidates": len(structure_candidates),
        "h1_aligned_candidates": int(h1_aligned.sum()),
        "h4_aligned_candidates": int(h4_aligned.sum()),
        "h1_h4_aligned_candidates": int((h1_aligned & h4_aligned).sum()),
        "aligned_displacement_fvg_candidates": len(fvg_candidates),
    }

    parent_counts = parent_signals.groupby("model_id").size()
    current_counts = signals.groupby("model_id").size()
    comparison_rows = []
    for model_id in MODEL_IDS:
        parent_count = int(parent_counts.get(model_id, 0))
        current_count = int(current_counts.get(model_id, 0))
        comparison_rows.append(
            {
                "model_id": model_id,
                "parent_opening_window_count": parent_count,
                "full_session_count": current_count,
                "added_count": current_count - parent_count,
            }
        )
    parent_comparison = pd.DataFrame.from_records(comparison_rows)

    setup_signals = signals[
        signals["model_id"].isin(
            {
                "p2_h4_sr",
                "p3_m15_structure",
                "p4_top_down_structure",
                "p5_top_down_structure_fvg",
            }
        )
    ]
    hour_counts = (
        setup_signals.groupby(
            ["model_id", "year", "session", "decision_local_hour"],
            sort=True,
        )
        .size()
        .rename("signal_count")
        .reset_index()
    )

    summary = {
        "phase": config.phase1_1.phase,
        "fingerprint": fingerprint,
        "parent_fingerprint": config.phase1_1.parent.fingerprint,
        "price_source": config.research.data.price_source,
        "source_role": config.research.data.source_role,
        "broker_specific_spread_claim": (
            config.execution.pricing.broker_specific_spread_claim
        ),
        "setup_signal_window": config.phase1_1.opportunity.setup_signal_window,
        "setup_selection": config.phase1_1.opportunity.setup_selection,
        "minimum_minutes_remaining": (
            config.phase1_1.opportunity.minimum_minutes_remaining
        ),
        "order_block_used": False,
        "h1_support_resistance_used": False,
        "fundamental_used": False,
        "opportunity_count": len(opportunities),
        "signal_counts": {
            model_id: int(signals["model_id"].eq(model_id).sum())
            for model_id in MODEL_IDS
        },
        "alignment_funnel": alignment_funnel,
        "p0_selected_directions": {
            row["session"]: row["direction"]
            for row in p0_fit[p0_fit["selected"]].to_dict("records")
        },
        "invariant_failure_count": sum(
            int(item.get("failure_count", 1)) for item in failures
        ),
        "invariant_failures": failures,
        "candidate_gates": gates,
        "any_candidate_passed": any(item["passed"] for item in gates.values()),
    }

    opportunities.to_parquet(output / "opportunities.parquet", index=False)
    signals.to_parquet(output / "signals.parquet", index=False)
    structure_candidates.to_parquet(
        output / "m15-structure-candidates.parquet", index=False
    )
    aligned_candidates.to_parquet(
        output / "m15-aligned-candidates.parquet", index=False
    )
    fvg_candidates.to_parquet(
        output / "m15-aligned-fvg-candidates.parquet", index=False
    )
    trades.to_parquet(output / "trades-primary.parquet", index=False)
    stress_trades.to_parquet(output / "trades-stress.parquet", index=False)
    panel.to_parquet(output / "opportunity-panel-primary.parquet", index=False)
    stress_panel.to_parquet(output / "opportunity-panel-stress.parquet", index=False)
    p0_fit.to_csv(output / "p0-fit.csv", index=False)
    metrics.to_csv(output / "metrics-primary.csv", index=False)
    stress_metrics.to_csv(output / "metrics-stress.csv", index=False)
    bootstrap.to_csv(output / "bootstrap.csv", index=False)
    parent_comparison.to_csv(output / "parent-signal-comparison.csv", index=False)
    hour_counts.to_csv(output / "signal-counts-by-local-hour.csv", index=False)
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True, default=_json_default) + "\n",
        encoding="utf-8",
    )
    manifest = {
        "phase": summary["phase"],
        "fingerprint": fingerprint,
        "parent_fingerprint": config.phase1_1.parent.fingerprint,
        "created_at": datetime.now(UTC).isoformat(),
        "input_hashes": input_hashes,
        "config_status": config.phase1_1.status,
        "artifact_files": sorted(path.name for path in output.iterdir()),
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return Phase1Result(artifact_directory=output, summary=summary)
