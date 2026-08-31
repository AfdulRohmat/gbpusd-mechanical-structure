"""Phase-3 return-blind price-action state and setup coverage audit."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from gbpusd_structure.config import ProjectConfig, load_project_config
from gbpusd_structure.phase0 import _fingerprint, _prepare_bars
from gbpusd_structure.phase1 import build_full_session_opportunities
from gbpusd_structure.phase2 import _load_construction_m5
from gbpusd_structure.price_action import (
    TREND_DOWN_STATES,
    TREND_UP_STATES,
    build_m15_price_action_states,
    congestion_status,
    prepare_m5_bars,
    signal_bar_quality,
)
from gbpusd_structure.structure import label_swings

STATE_NAMES = {
    "undetermined",
    "trend_up_active",
    "trend_down_active",
    "trend_up_break_pending_extreme",
    "trend_down_break_pending_extreme",
    "post_up_extreme_transition",
    "post_down_extreme_transition",
    "range",
    "range_break_up_pending",
    "range_break_down_pending",
    "range_break_up_wait_retest",
    "range_break_down_wait_retest",
}
FORBIDDEN_OUTPUT_TOKENS = ("return", "pnl", "profit", "win_rate", "exit", "net_r")


@dataclass(frozen=True)
class Phase3Result:
    artifact_directory: Path
    summary: dict[str, Any]


def _json_default(value: Any) -> Any:
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    if isinstance(value, np.generic):
        return value.item()
    raise TypeError(f"Cannot serialize {type(value)!r}")


def assign_states_to_sessions(
    states: pd.DataFrame,
    opportunities: pd.DataFrame,
) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    for opportunity in opportunities.to_dict("records"):
        mask = states["timestamp"].ge(opportunity["session_open_at"])
        mask &= states["available_at"].lt(opportunity["cutoff_at"])
        for state in states[mask].to_dict("records"):
            records.append({**state, **opportunity})
    return pd.DataFrame.from_records(records)


def _latest_state_position(
    available_values: np.ndarray,
    at: pd.Timestamp,
) -> int | None:
    position = int(np.searchsorted(available_values, at.value, side="right") - 1)
    return position if position >= 0 else None


def _projected_trendline(state: pd.Series, at: pd.Timestamp) -> float | None:
    value = state.get("trendline_value_at_available")
    slope = state.get("trendline_slope_per_minute")
    if pd.isna(value) or pd.isna(slope):
        return None
    minutes = (at - pd.Timestamp(state["available_at"])).total_seconds() / 60
    return float(value) + float(slope) * minutes


def _key_entry_sources(
    bar: pd.Series,
    state: pd.Series,
    direction: str,
    config: ProjectConfig,
) -> tuple[list[str], dict[str, float | None]]:
    atr = float(state["atr"])
    tolerance = config.phase3.m5_setup.key_entry_tolerance_m15_atr * atr
    low = float(bar["mid_low"])
    high = float(bar["mid_high"])
    signal_available = pd.Timestamp(bar["available_at"])
    levels: dict[str, float | None] = {
        "ema21": None,
        "projected_m15_trendline": None,
    }
    sources: list[str] = []
    ema = state.get("ema21")
    if pd.notna(ema):
        levels["ema21"] = float(ema)
        if low - tolerance <= float(ema) <= high + tolerance:
            sources.append("ema21")
    line = _projected_trendline(state, signal_available)
    if line is not None:
        levels["projected_m15_trendline"] = line
        if low - tolerance <= line <= high + tolerance:
            sources.append("projected_m15_trendline")
    expected = "long" if state["state"] in TREND_UP_STATES else "short"
    if direction != expected:
        return [], levels
    return sources, levels


def _entry_trigger(
    bars: pd.DataFrame,
    signal_position: int,
    direction: str,
    cutoff: pd.Timestamp,
    config: ProjectConfig,
) -> tuple[float, pd.Timestamp | None, str | None]:
    signal = bars.iloc[signal_position]
    buffer = (
        config.phase3.m5_setup.entry_trigger_buffer_pips
        * config.research.instrument.pip_size
    )
    if direction == "long":
        trigger_price = float(signal["ask_high"]) + buffer
    else:
        trigger_price = float(signal["bid_low"]) - buffer
    end = min(
        len(bars),
        signal_position + config.phase3.m5_setup.entry_trigger_valid_bars + 1,
    )
    for position in range(signal_position + 1, end):
        candidate = bars.iloc[position]
        if pd.Timestamp(candidate["timestamp"]) >= cutoff:
            break
        touched = (
            float(candidate["ask_high"]) >= trigger_price
            if direction == "long"
            else float(candidate["bid_low"]) <= trigger_price
        )
        if touched:
            return (
                trigger_price,
                pd.Timestamp(candidate["available_at"]),
                str(candidate["bar_id"]),
            )
    return trigger_price, None, None


def _setup_record(
    *,
    opportunity: dict[str, Any],
    family: str,
    direction: str,
    bar: pd.Series,
    m15_state: pd.Series | None,
    context_event_id: str | None,
    key_sources: list[str],
    key_levels: dict[str, float | None],
    signal_pass: bool,
    signal_metrics: dict[str, float],
    congestion_veto: bool,
    congestion_range_atr: float | None,
    congestion_overlap: float | None,
    trigger_price: float,
    triggered_at: pd.Timestamp | None,
    trigger_bar_id: str | None,
) -> dict[str, Any]:
    available = pd.Timestamp(bar["available_at"])
    eligible = bool(signal_pass and key_sources and not congestion_veto)
    return {
        **opportunity,
        "setup_id": (
            f"setup:{family}:{opportunity['opportunity_id']}:{available.isoformat()}"
        ),
        "family": family,
        "direction": direction,
        "signal_bar_id": str(bar["bar_id"]),
        "signal_at": pd.Timestamp(bar["timestamp"]),
        "available_at": available,
        "feature_available_at": available,
        "m15_state_available_at": (
            pd.Timestamp(m15_state["available_at"])
            if m15_state is not None
            else available
        ),
        "m15_state": m15_state["state"] if m15_state is not None else None,
        "m15_atr": float(m15_state["atr"]) if m15_state is not None else None,
        "context_event_id": context_event_id,
        "key_entry_sources": json.dumps(key_sources, separators=(",", ":")),
        "ema21_level": key_levels.get("ema21"),
        "trendline_level": key_levels.get("projected_m15_trendline"),
        "range_boundary_level": key_levels.get("frozen_range_boundary"),
        "signal_quality_pass": signal_pass,
        "signal_body_fraction": signal_metrics["body_fraction"],
        "signal_close_location": signal_metrics["close_location"],
        "signal_range_m5_atr": signal_metrics["range_atr"],
        "congestion_veto": congestion_veto,
        "congestion_total_range_m5_atr": congestion_range_atr,
        "congestion_mean_overlap": congestion_overlap,
        "eligible_signal": eligible,
        "trigger_price": trigger_price,
        "triggered": triggered_at is not None,
        "triggered_at": triggered_at,
        "trigger_bar_id": trigger_bar_id,
    }


def build_trend_second_entry_candidates(
    m5: pd.DataFrame,
    states: pd.DataFrame,
    opportunities: pd.DataFrame,
    config: ProjectConfig,
) -> pd.DataFrame:
    """Build causal with-trend second-attempt signal candidates."""

    state_ordered = states.sort_values("available_at", kind="stable").reset_index(
        drop=True
    )
    state_values = (
        pd.to_datetime(state_ordered["available_at"], utc=True)
        .astype("int64")
        .to_numpy()
    )
    timestamps = pd.to_datetime(m5["timestamp"], utc=True)
    records: list[dict[str, Any]] = []
    settings = config.phase3.m5_setup

    for opportunity in opportunities.to_dict("records"):
        positions = np.flatnonzero(
            (
                timestamps.ge(opportunity["session_open_at"])
                & timestamps.lt(opportunity["cutoff_at"])
            ).to_numpy()
        )
        stage = "idle"
        active_direction: str | None = None
        age = 0
        leg1_extreme: float | None = None
        resume_level: float | None = None

        for local_index, position in enumerate(positions):
            if local_index == 0:
                continue
            bar = m5.iloc[position]
            previous = m5.iloc[positions[local_index - 1]]
            state_position = _latest_state_position(
                state_values, pd.Timestamp(bar["available_at"])
            )
            if state_position is None:
                stage = "idle"
                continue
            state = state_ordered.iloc[state_position]
            direction = (
                "long"
                if state["state"] in TREND_UP_STATES
                else "short"
                if state["state"] in TREND_DOWN_STATES
                else None
            )
            if direction is None or not bool(bar["structure_eligible"]):
                stage = "idle"
                active_direction = None
                continue
            if direction != active_direction:
                stage = "idle"
                active_direction = direction
                age = 0
                leg1_extreme = None
                resume_level = None
            m15_atr = float(state["atr"])
            buffer = settings.leg_new_extreme_buffer_m15_atr * m15_atr
            starts_pullback = (
                float(bar["mid_low"]) < float(previous["mid_low"]) - buffer
                if direction == "long"
                else float(bar["mid_high"]) > float(previous["mid_high"]) + buffer
            )
            reversal_attempt = (
                float(bar["mid_high"]) > float(previous["mid_high"])
                if direction == "long"
                else float(bar["mid_low"]) < float(previous["mid_low"])
            )

            if stage == "idle" and starts_pullback:
                stage = "leg1"
                age = 0
                leg1_extreme = (
                    float(bar["mid_low"])
                    if direction == "long"
                    else float(bar["mid_high"])
                )
                resume_level = (
                    float(state["trend_extreme"])
                    if pd.notna(state["trend_extreme"])
                    else None
                )
                continue
            if stage == "idle":
                continue

            age += 1
            resumed = bool(
                resume_level is not None
                and (
                    float(bar["mid_high"]) >= resume_level
                    if direction == "long"
                    else float(bar["mid_low"]) <= resume_level
                )
            )
            if age > settings.maximum_bars_between_pullback_attempts or resumed:
                stage = "idle"
                continue

            if stage == "leg1":
                if direction == "long":
                    leg1_extreme = min(float(leg1_extreme), float(bar["mid_low"]))
                else:
                    leg1_extreme = max(float(leg1_extreme), float(bar["mid_high"]))
                if reversal_attempt:
                    stage = "attempt1"
                continue

            if stage == "attempt1":
                new_second_leg = (
                    float(bar["mid_low"]) < float(leg1_extreme) - buffer
                    if direction == "long"
                    else float(bar["mid_high"]) > float(leg1_extreme) + buffer
                )
                if new_second_leg:
                    stage = "leg2"
                continue

            if stage == "leg2" and reversal_attempt:
                signal_pass, signal_metrics = signal_bar_quality(bar, direction, config)
                key_sources, key_levels = _key_entry_sources(
                    bar, state, direction, config
                )
                veto, congestion_range, congestion_overlap = congestion_status(
                    m5, position, config
                )
                trigger_price, triggered_at, trigger_bar_id = _entry_trigger(
                    m5,
                    position,
                    direction,
                    pd.Timestamp(opportunity["cutoff_at"]),
                    config,
                )
                records.append(
                    _setup_record(
                        opportunity=opportunity,
                        family="with_trend_second_entry",
                        direction=direction,
                        bar=bar,
                        m15_state=state,
                        context_event_id=None,
                        key_sources=key_sources,
                        key_levels=key_levels,
                        signal_pass=signal_pass,
                        signal_metrics=signal_metrics,
                        congestion_veto=veto,
                        congestion_range_atr=congestion_range,
                        congestion_overlap=congestion_overlap,
                        trigger_price=trigger_price,
                        triggered_at=triggered_at,
                        trigger_bar_id=trigger_bar_id,
                    )
                )
                stage = "idle"
    return pd.DataFrame.from_records(records)


def _opportunity_for_event(
    event: dict[str, Any],
    opportunities: pd.DataFrame,
) -> dict[str, Any] | None:
    available = pd.Timestamp(event["available_at"])
    matches = opportunities[
        opportunities["session_open_at"].lt(available)
        & opportunities["cutoff_at"].gt(available)
    ]
    if matches.empty:
        return None
    if len(matches) > 1:
        raise ValueError(
            f"Context event overlaps multiple sessions: {event['event_id']}"
        )
    return matches.iloc[0].to_dict()


def build_range_setup_candidates(
    m5: pd.DataFrame,
    context_events: pd.DataFrame,
    states: pd.DataFrame,
    opportunities: pd.DataFrame,
    config: ProjectConfig,
) -> pd.DataFrame:
    """Build post-confirmation range-fade and breakout-pullback signals."""

    if context_events.empty:
        return pd.DataFrame()
    timestamps = pd.to_datetime(m5["timestamp"], utc=True)
    state_ordered = states.sort_values("available_at", kind="stable").reset_index(
        drop=True
    )
    state_values = (
        pd.to_datetime(state_ordered["available_at"], utc=True)
        .astype("int64")
        .to_numpy()
    )
    records: list[dict[str, Any]] = []
    wait = config.phase3.m5_setup.signal_wait_bars_after_m15_event

    for event in context_events.to_dict("records"):
        opportunity = _opportunity_for_event(event, opportunities)
        if opportunity is None:
            continue
        event_available = pd.Timestamp(event["available_at"])
        start = int(np.searchsorted(timestamps.astype("int64"), event_available.value))
        family = (
            "failed_range_break_fade"
            if event["event_type"] == "failed_range_break"
            else "accepted_breakout_pullback"
        )
        direction = str(event["direction"])
        boundary = float(event["key_boundary"])
        tolerance = config.phase3.m5_setup.key_entry_tolerance_m15_atr * float(
            event["atr"]
        )
        for position in range(start, min(len(m5), start + wait)):
            bar = m5.iloc[position]
            if pd.Timestamp(bar["timestamp"]) >= pd.Timestamp(opportunity["cutoff_at"]):
                break
            signal_pass, signal_metrics = signal_bar_quality(bar, direction, config)
            intersects = (
                float(bar["mid_low"]) - tolerance
                <= boundary
                <= float(bar["mid_high"]) + tolerance
            )
            if not signal_pass or not intersects:
                continue
            veto, congestion_range, congestion_overlap = congestion_status(
                m5, position, config
            )
            state_position = _latest_state_position(
                state_values, pd.Timestamp(bar["available_at"])
            )
            state = (
                state_ordered.iloc[state_position]
                if state_position is not None
                else None
            )
            trigger_price, triggered_at, trigger_bar_id = _entry_trigger(
                m5,
                position,
                direction,
                pd.Timestamp(opportunity["cutoff_at"]),
                config,
            )
            records.append(
                _setup_record(
                    opportunity=opportunity,
                    family=family,
                    direction=direction,
                    bar=bar,
                    m15_state=state,
                    context_event_id=str(event["event_id"]),
                    key_sources=["frozen_range_boundary"],
                    key_levels={"frozen_range_boundary": boundary},
                    signal_pass=signal_pass,
                    signal_metrics=signal_metrics,
                    congestion_veto=veto,
                    congestion_range_atr=congestion_range,
                    congestion_overlap=congestion_overlap,
                    trigger_price=trigger_price,
                    triggered_at=triggered_at,
                    trigger_bar_id=trigger_bar_id,
                )
            )
            break
    return pd.DataFrame.from_records(records)


def select_session_setups(
    candidates: pd.DataFrame,
    config: ProjectConfig,
) -> pd.DataFrame:
    if candidates.empty:
        output = candidates.copy()
        for column, dtype in (
            ("family", "object"),
            ("session", "object"),
            ("direction", "object"),
            ("eligible_signal", "bool"),
            ("triggered", "bool"),
        ):
            if column not in output:
                output[column] = pd.Series(dtype=dtype)
        output["selected"] = pd.Series(dtype="bool")
        output["selection_rank"] = pd.Series(dtype="int64")
        return output
    family_order = {
        family: index
        for index, family in enumerate(config.phase3.m5_setup.setup_families)
    }
    output = candidates.copy()
    output["_family_order"] = output["family"].map(family_order)
    output = output.sort_values(
        ["available_at", "_family_order", "setup_id"], kind="stable"
    ).reset_index(drop=True)
    output["selection_rank"] = (
        output[output["eligible_signal"]]
        .groupby("opportunity_id", sort=False)
        .cumcount()
        .add(1)
        .reindex(output.index)
    )
    caps = output["session"].map(
        config.phase3.m5_setup.maximum_selected_setups_per_session
    )
    output["selected"] = (
        output["eligible_signal"]
        & output["selection_rank"].notna()
        & output["selection_rank"].le(caps)
    )
    return output.drop(columns="_family_order")


def _invariant_failures(
    m15: pd.DataFrame,
    states: pd.DataFrame,
    session_states: pd.DataFrame,
    transitions: pd.DataFrame,
    context_events: pd.DataFrame,
    setups: pd.DataFrame,
    config: ProjectConfig,
) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []

    def add(name: str, count: int) -> None:
        if count:
            failures.append({"invariant": name, "failure_count": int(count)})

    add("one_state_per_m15_bar", abs(len(states) - len(m15)))
    add("unique_m15_state_bar", int(states["bar_id"].duplicated().sum()))
    add("known_state_name", int((~states["state"].isin(STATE_NAMES)).sum()))
    anchors = states[states["trendline_anchors_available_at"].notna()]
    add(
        "trendline_anchors_available_by_snapshot",
        int(
            anchors["trendline_anchors_available_at"].gt(anchors["available_at"]).sum()
        ),
    )
    range_rows = states[states["range_id"].notna()]
    add(
        "valid_frozen_range_bounds",
        int(range_rows["range_lower"].ge(range_rows["range_upper"]).sum()),
    )
    for _, frame in range_rows.groupby("range_id"):
        if frame["range_lower"].nunique() > 1 or frame["range_upper"].nunique() > 1:
            failures.append(
                {"invariant": "frozen_range_boundaries", "failure_count": 1}
            )
    add(
        "unique_session_state_membership",
        int(session_states.duplicated(["bar_id", "opportunity_id"]).sum()),
    )
    if not setups.empty:
        add(
            "features_available_by_signal",
            int(setups["feature_available_at"].gt(setups["available_at"]).sum()),
        )
        triggered = setups[setups["triggered"]]
        add(
            "trigger_strictly_after_signal",
            int(triggered["triggered_at"].le(triggered["available_at"]).sum()),
        )
        add(
            "selected_subset_of_eligible",
            int((setups["selected"] & ~setups["eligible_signal"]).sum()),
        )
        selected_counts = setups[setups["selected"]].groupby("opportunity_id").size()
        opportunity_sessions = setups.drop_duplicates("opportunity_id").set_index(
            "opportunity_id"
        )["session"]
        cap_failures = 0
        for opportunity_id, count in selected_counts.items():
            session = opportunity_sessions.loc[opportunity_id]
            cap = config.phase3.m5_setup.maximum_selected_setups_per_session[session]
            cap_failures += int(count > cap)
        add("session_setup_cap", cap_failures)
        add(
            "construction_year_only",
            int(pd.to_datetime(setups["session_date"]).dt.year.ne(2024).sum()),
        )
    for name, frame in (
        ("states", states),
        ("transitions", transitions),
        ("context_events", context_events),
        ("setups", setups),
    ):
        forbidden = [
            column
            for column in frame.columns
            if any(token in column.lower() for token in FORBIDDEN_OUTPUT_TOKENS)
        ]
        if forbidden:
            failures.append(
                {
                    "invariant": f"{name}_contains_forbidden_outcome_columns",
                    "columns": forbidden,
                }
            )
    return failures


def _coverage_summary(
    session_states: pd.DataFrame,
    setups: pd.DataFrame,
    failures: list[dict[str, Any]],
    config: ProjectConfig,
) -> tuple[dict[str, Any], dict[str, Any]]:
    eligible_states = session_states[session_states["structure_eligible"]]
    classified_fraction = float(eligible_states["state"].ne("undetermined").mean())
    eligible_setups = setups[setups["eligible_signal"]]
    selected = setups[setups["selected"]]
    triggered = selected[selected["triggered"]]
    trigger_rate = len(triggered) / len(selected) if len(selected) else 0.0
    session_counts = {
        session: int(triggered["session"].eq(session).sum())
        for session in ("london", "new_york")
    }
    direction_counts = {
        direction: int(triggered["direction"].eq(direction).sum())
        for direction in ("long", "short")
    }
    gate = config.phase3.coverage_gate
    checks = {
        "zero_invariant_failures": not failures,
        "minimum_classified_m15_fraction": classified_fraction
        >= gate.minimum_classified_m15_fraction,
        "minimum_setup_signals": len(selected) >= gate.minimum_setup_signals_per_year,
        "minimum_triggered_setups": len(triggered)
        >= gate.minimum_triggered_setups_per_year,
        "minimum_trigger_rate": trigger_rate >= gate.minimum_trigger_rate,
        "minimum_each_session": all(
            count >= gate.minimum_each_session for count in session_counts.values()
        ),
        "minimum_each_direction": all(
            count >= gate.minimum_each_direction for count in direction_counts.values()
        ),
    }
    return (
        {
            "classified_m15_fraction": classified_fraction,
            "raw_candidate_count": len(setups),
            "eligible_signal_count": len(eligible_setups),
            "selected_signal_count": len(selected),
            "triggered_selected_count": len(triggered),
            "trigger_rate": trigger_rate,
            "desired_frequency_met": (
                gate.desired_triggered_setups_per_year[0]
                <= len(triggered)
                <= gate.desired_triggered_setups_per_year[1]
            ),
            "family_counts": {
                family: {
                    "raw": int(setups["family"].eq(family).sum()),
                    "eligible": int(eligible_setups["family"].eq(family).sum()),
                    "selected": int(selected["family"].eq(family).sum()),
                    "triggered": int(triggered["family"].eq(family).sum()),
                }
                for family in config.phase3.m5_setup.setup_families
            },
            "session_trigger_counts": session_counts,
            "direction_trigger_counts": direction_counts,
        },
        {"passed": all(checks.values()), "checks": checks},
    )


def run_phase3_state_coverage(
    project_root: Path,
    data_root: Path,
    *,
    artifact_root: Path | None = None,
) -> Phase3Result:
    """Run Phase 3 state construction and setup coverage without outcomes."""

    config = load_project_config(project_root / "config")
    if config.phase3.scope.construction_year != config.phase2.scope.construction_year:
        raise ValueError("Phase 3 and construction-only loader years differ")
    m5_raw, input_paths = _load_construction_m5(data_root, config)
    fingerprint, input_hashes = _fingerprint(project_root, input_paths)
    output = (
        artifact_root or project_root / "artifacts" / "phase3" / "coverage"
    ) / fingerprint
    output.mkdir(parents=True, exist_ok=True)

    bars = _prepare_bars(m5_raw, config)
    m15 = bars["15min"]
    swings = label_swings(
        m15,
        config.structure,
        pip_size=config.research.instrument.pip_size,
    )
    states, transitions, context_events = build_m15_price_action_states(
        m15, swings, config
    )
    m5 = prepare_m5_bars(m5_raw, config)
    opportunities = build_full_session_opportunities(m5_raw, config)
    opportunities = opportunities[
        opportunities["year"].eq(config.phase3.scope.construction_year)
    ].reset_index(drop=True)
    session_states = assign_states_to_sessions(states, opportunities)
    trend_candidates = build_trend_second_entry_candidates(
        m5, states, opportunities, config
    )
    range_candidates = build_range_setup_candidates(
        m5, context_events, states, opportunities, config
    )
    candidate_frames = [
        frame.dropna(axis=1, how="all")
        for frame in (trend_candidates, range_candidates)
        if not frame.empty
    ]
    candidates = (
        pd.concat(candidate_frames, ignore_index=True, sort=False)
        if candidate_frames
        else pd.DataFrame()
    )
    setups = select_session_setups(candidates, config)
    failures = _invariant_failures(
        m15,
        states,
        session_states,
        transitions,
        context_events,
        setups,
        config,
    )
    coverage, gate = _coverage_summary(session_states, setups, failures, config)
    state_counts = {
        str(state): int(count)
        for state, count in session_states["state"].value_counts().items()
    }
    transition_counts = (
        {
            str(cause): int(count)
            for cause, count in transitions["cause"].value_counts().items()
        }
        if "cause" in transitions
        else {}
    )
    context_event_counts = {
        event_type: (
            int(context_events["event_type"].eq(event_type).sum())
            if "event_type" in context_events
            else 0
        )
        for event_type in ("failed_range_break", "accepted_breakout_pullback")
    }
    summary = {
        "phase": config.phase3.phase,
        "fingerprint": fingerprint,
        "config_status": config.phase3.status,
        "construction_year": config.phase3.scope.construction_year,
        "historical_replication_files_opened": False,
        "returns_accessed": False,
        "pnl_accessed": False,
        "m5_bar_count": len(m5),
        "m15_bar_count": len(m15),
        "session_opportunity_count": len(opportunities),
        "in_session_m15_count": len(session_states),
        "state_counts": state_counts,
        "transition_counts": transition_counts,
        "context_event_counts": context_event_counts,
        "coverage": coverage,
        "invariant_failure_count": len(failures),
        "invariant_failures": failures,
        "coverage_gate": gate,
        "construction_pnl_permitted": bool(gate["passed"] and not failures),
        "decision": (
            "freeze_before_construction_pnl"
            if gate["passed"] and not failures
            else "stop_without_pnl"
        ),
    }

    states.to_parquet(output / "m15-states.parquet", index=False)
    session_states.to_parquet(output / "m15-session-states.parquet", index=False)
    transitions.to_parquet(output / "m15-transitions.parquet", index=False)
    context_events.to_parquet(output / "m15-context-events.parquet", index=False)
    setups.to_parquet(output / "m5-setup-coverage.parquet", index=False)
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True, default=_json_default) + "\n",
        encoding="utf-8",
    )
    manifest = {
        "phase": config.phase3.phase,
        "fingerprint": fingerprint,
        "created_at": datetime.now(UTC).isoformat(),
        "input_hashes": input_hashes,
        "historical_replication_files_opened": False,
        "returns_accessed": False,
        "pnl_accessed": False,
        "artifact_files": sorted(path.name for path in output.iterdir()),
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return Phase3Result(artifact_directory=output, summary=summary)
