"""Phase-2 gross directional event study for causal M15 primitives."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from gbpusd_structure.config import ProjectConfig, load_project_config
from gbpusd_structure.data import (
    REQUIRED_M5_COLUMNS,
    canonical_m5_paths,
)
from gbpusd_structure.phase0 import _fingerprint, _prepare_bars
from gbpusd_structure.phase1 import (
    _latest_state,
    build_full_session_opportunities,
)
from gbpusd_structure.structure import (
    label_structure_state_machine,
    label_swings,
)

PRIMITIVES = ("bos", "choch", "liquidity_sweep", "displacement")
BASELINE_RULES = (
    "event_direction",
    "seeded_random_direction",
    "session_momentum",
    "session_mean_reversion",
    "four_bar_close_breakout",
)


@dataclass(frozen=True)
class Phase2Result:
    artifact_directory: Path
    summary: dict[str, Any]


def _json_default(value: Any) -> Any:
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    if isinstance(value, np.generic):
        return value.item()
    raise TypeError(f"Cannot serialize {type(value)!r}")


def _load_construction_m5(
    data_root: Path,
    config: ProjectConfig,
) -> tuple[pd.DataFrame, list[Path]]:
    """Read only construction-year files; do not open historical replication."""

    year = config.phase2.scope.construction_year
    selected = [
        path
        for path in canonical_m5_paths(data_root, config.research)
        if path.stem.startswith(f"m5-{year}-")
    ]
    if len(selected) != 12:
        raise ValueError(
            f"Phase 2 requires 12 construction months, found {len(selected)}"
        )
    frames: list[pd.DataFrame] = []
    for path in selected:
        frame = pd.read_parquet(path)
        missing = sorted(REQUIRED_M5_COLUMNS.difference(frame.columns))
        if missing:
            raise ValueError(
                f"Canonical M5 schema error in {path.name}: " + ", ".join(missing)
            )
        frames.append(frame)
    bars = pd.concat(frames, ignore_index=True)
    bars["timestamp"] = pd.to_datetime(bars["timestamp"], utc=True)
    start = pd.Timestamp(year=year, month=1, day=1, tz="UTC")
    end = pd.Timestamp(year=year + 1, month=1, day=1, tz="UTC")
    bars = bars[bars["timestamp"].ge(start) & bars["timestamp"].lt(end)]
    bars = bars.sort_values("timestamp", kind="stable").reset_index(drop=True)
    if bars.empty or bars["timestamp"].duplicated().any():
        raise ValueError("Phase 2 construction M5 data is empty or duplicated")
    return bars, selected


def label_liquidity_sweeps(
    m15: pd.DataFrame,
    swings: pd.DataFrame,
    *,
    minimum_excursion_atr: float,
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Label first causal wick excursion through each latest confirmed swing."""

    ordered_swings = swings.sort_values(
        ["available_at", "event_id"], kind="stable"
    ).to_dict("records")
    pointer = 0
    active: dict[str, dict[str, Any] | None] = {"high": None, "low": None}
    records: list[dict[str, Any]] = []
    stats = {"high_excursions": 0, "low_excursions": 0, "ambiguous_bars": 0}

    for _index, bar in m15.reset_index(drop=True).iterrows():
        bar_start = pd.Timestamp(bar["timestamp"])
        while (
            pointer < len(ordered_swings)
            and pd.Timestamp(ordered_swings[pointer]["available_at"]) <= bar_start
        ):
            swing = ordered_swings[pointer]
            kind = "high" if swing["event_type"] == "swing_high" else "low"
            active[kind] = swing
            pointer += 1
        if not bool(bar["structure_eligible"]) or not np.isfinite(bar["atr"]):
            continue
        atr = float(bar["atr"])
        if atr <= 0:
            continue
        buffer = minimum_excursion_atr * atr
        candidates: list[dict[str, Any]] = []

        high = active["high"]
        if high is not None and float(bar["mid_high"]) >= float(high["price"]) + buffer:
            stats["high_excursions"] += 1
            if float(bar["mid_close"]) <= float(high["price"]):
                candidates.append(
                    {
                        "source": high,
                        "swept_side": "high",
                        "direction": "short",
                        "source_direction": "down",
                        "wick_excursion_atr": (
                            float(bar["mid_high"]) - float(high["price"])
                        )
                        / atr,
                    }
                )
            active["high"] = None

        low = active["low"]
        if low is not None and float(bar["mid_low"]) <= float(low["price"]) - buffer:
            stats["low_excursions"] += 1
            if float(bar["mid_close"]) >= float(low["price"]):
                candidates.append(
                    {
                        "source": low,
                        "swept_side": "low",
                        "direction": "long",
                        "source_direction": "up",
                        "wick_excursion_atr": (
                            float(low["price"]) - float(bar["mid_low"])
                        )
                        / atr,
                    }
                )
            active["low"] = None

        if len(candidates) > 1:
            stats["ambiguous_bars"] += 1
            continue
        if not candidates:
            continue
        candidate = candidates[0]
        source = candidate["source"]
        records.append(
            {
                "event_id": (
                    f"sweep:15min:{bar_start.isoformat()}:{candidate['swept_side']}"
                ),
                "primitive": "liquidity_sweep",
                "event_type": "liquidity_sweep",
                "event_at": bar_start,
                "available_at": pd.Timestamp(bar["available_at"]),
                "direction": candidate["direction"],
                "source_direction": candidate["source_direction"],
                "atr": atr,
                "body_atr": float(bar["body_atr"]),
                "bar_id": str(bar["bar_id"]),
                "source_swing_id": str(source["event_id"]),
                "source_swing_available_at": pd.Timestamp(source["available_at"]),
                "swept_side": candidate["swept_side"],
                "swept_level": float(source["price"]),
                "wick_excursion_atr": candidate["wick_excursion_atr"],
            }
        )
    return pd.DataFrame.from_records(records), stats


def label_displacements(
    m15: pd.DataFrame,
    *,
    minimum_body_atr: float,
) -> pd.DataFrame:
    """Label completed directional M15 bodies above the frozen ATR threshold."""

    eligible = m15[m15["structure_eligible"] & m15["body_atr"].ge(minimum_body_atr)]
    records: list[dict[str, Any]] = []
    for bar in eligible.to_dict("records"):
        open_price = float(bar["mid_open"])
        close_price = float(bar["mid_close"])
        if np.isclose(open_price, close_price, rtol=0, atol=1e-12):
            continue
        direction = "long" if close_price > open_price else "short"
        records.append(
            {
                "event_id": f"displacement:15min:{bar['timestamp'].isoformat()}",
                "primitive": "displacement",
                "event_type": "displacement",
                "event_at": pd.Timestamp(bar["timestamp"]),
                "available_at": pd.Timestamp(bar["available_at"]),
                "direction": direction,
                "source_direction": "up" if direction == "long" else "down",
                "atr": float(bar["atr"]),
                "body_atr": float(bar["body_atr"]),
                "bar_id": str(bar["bar_id"]),
                "source_swing_id": None,
                "source_swing_available_at": pd.NaT,
                "swept_side": None,
                "swept_level": None,
                "wick_excursion_atr": None,
            }
        )
    return pd.DataFrame.from_records(records)


def _break_events(breaks: pd.DataFrame) -> pd.DataFrame:
    eligible = breaks[breaks["event_type"].isin(["bos", "choch"])]
    records: list[dict[str, Any]] = []
    for event in eligible.to_dict("records"):
        records.append(
            {
                "event_id": str(event["event_id"]),
                "primitive": str(event["event_type"]),
                "event_type": str(event["event_type"]),
                "event_at": pd.Timestamp(event["event_at"]),
                "available_at": pd.Timestamp(event["available_at"]),
                "direction": "long" if event["direction"] == "up" else "short",
                "source_direction": str(event["direction"]),
                "atr": float(event["atr"]),
                "body_atr": float(event["body_atr"]),
                "bar_id": str(event["bar_id"]),
                "source_swing_id": str(event["broken_swing_id"]),
                "source_swing_available_at": pd.NaT,
                "swept_side": None,
                "swept_level": float(event["broken_level"]),
                "wick_excursion_atr": None,
            }
        )
    return pd.DataFrame.from_records(records)


def assign_events_to_sessions(
    events: pd.DataFrame,
    opportunities: pd.DataFrame,
) -> pd.DataFrame:
    """Attach each event to its non-overlapping registered session window."""

    records: list[dict[str, Any]] = []
    if events.empty:
        return pd.DataFrame()
    ordered = events.sort_values(["available_at", "event_id"], kind="stable")
    for opportunity in opportunities.to_dict("records"):
        mask = ordered["event_at"].ge(opportunity["session_open_at"])
        mask &= ordered["available_at"].gt(opportunity["session_open_at"])
        mask &= ordered["available_at"].lt(opportunity["cutoff_at"])
        for event in ordered[mask].to_dict("records"):
            records.append({**event, **opportunity})
    return (
        pd.DataFrame.from_records(records)
        .sort_values(["available_at", "primitive", "event_id"], kind="stable")
        .reset_index(drop=True)
    )


def select_primary_events(events: pd.DataFrame) -> pd.DataFrame:
    """Keep the first event of each primitive in each session opportunity."""

    if events.empty:
        return events.copy()
    return (
        events.sort_values(["available_at", "event_id"], kind="stable")
        .groupby(["primitive", "opportunity_id"], sort=False, as_index=False)
        .head(1)
        .sort_values(["available_at", "primitive"], kind="stable")
        .reset_index(drop=True)
    )


def _stable_random_direction(event_id: str, seed: int) -> str:
    digest = hashlib.sha256(f"{seed}:{event_id}".encode()).digest()
    return "long" if digest[0] & 1 else "short"


def _context_alignment(direction: str, h1: str, h4: str) -> str:
    expected = "bullish" if direction == "long" else "bearish"
    opposite = "bearish" if direction == "long" else "bullish"
    if h1 == expected and h4 == expected:
        return "both_aligned"
    if h1 == opposite and h4 == opposite:
        return "both_opposed"
    if h1 in {"bullish", "bearish"} and h4 in {"bullish", "bearish"}:
        return "mixed"
    return "undetermined"


def _displacement_bucket(body_atr: float, boundaries: tuple[float, float]) -> str:
    lower, upper = boundaries
    if body_atr < lower:
        return "below_0_8"
    if body_atr < upper:
        return "0_8_to_1_2"
    return "at_least_1_2"


def attach_event_features(
    events: pd.DataFrame,
    m5: pd.DataFrame,
    m15: pd.DataFrame,
    contexts: dict[str, pd.DataFrame],
    config: ProjectConfig,
) -> pd.DataFrame:
    """Attach only causal context and simple baseline directions."""

    if events.empty:
        return events.copy()
    m5_by_time = m5.set_index("timestamp")
    m15_ordered = m15.reset_index(drop=True)
    m15_by_bar = {
        str(value): index for index, value in enumerate(m15_ordered["bar_id"])
    }
    lookback = config.phase2.baselines.recent_breakout_lookback_m15_bars
    seed = config.phase2.baselines.random_seed
    boundaries = config.phase2.reporting.displacement_strength_boundaries_atr
    records: list[dict[str, Any]] = []

    for event in events.to_dict("records"):
        decision = pd.Timestamp(event["available_at"])
        session_open = pd.Timestamp(event["session_open_at"])
        if session_open not in m5_by_time.index:
            raise ValueError(
                f"Missing session-open M5 bar for {event['opportunity_id']}"
            )
        session_open_mid = float(m5_by_time.loc[session_open, "mid_open"])
        bar_index = m15_by_bar.get(str(event["bar_id"]))
        if bar_index is None:
            raise ValueError(f"Unknown M15 bar for {event['event_id']}")
        event_bar = m15_ordered.iloc[bar_index]
        event_close = float(event_bar["mid_close"])
        if event_close > session_open_mid:
            momentum = "long"
            mean_reversion = "short"
        elif event_close < session_open_mid:
            momentum = "short"
            mean_reversion = "long"
        else:
            momentum = None
            mean_reversion = None

        breakout = None
        if bar_index >= lookback:
            previous = m15_ordered.iloc[bar_index - lookback : bar_index]
            if bool(previous["structure_eligible"].all()):
                if event_close > float(previous["mid_high"].max()):
                    breakout = "long"
                elif event_close < float(previous["mid_low"].min()):
                    breakout = "short"

        h1 = _latest_state(contexts["1H"], decision)
        h4 = _latest_state(contexts["4H"], decision)
        direction = str(event["direction"])
        records.append(
            {
                **event,
                "h1_context": h1,
                "h4_context": h4,
                "context_alignment": _context_alignment(direction, h1, h4),
                "displacement_strength": _displacement_bucket(
                    float(event["body_atr"]), boundaries
                ),
                "event_direction": direction,
                "seeded_random_direction": _stable_random_direction(
                    str(event["event_id"]), seed
                ),
                "session_momentum": momentum,
                "session_mean_reversion": mean_reversion,
                "four_bar_close_breakout": breakout,
                "session_open_mid": session_open_mid,
                "event_bar_close_mid": event_close,
                "baseline_feature_available_at": decision,
            }
        )
    return pd.DataFrame.from_records(records)


def _barrier_label(
    favorable: np.ndarray,
    adverse: np.ndarray,
    threshold: float,
) -> str:
    favorable_positions = np.flatnonzero(favorable >= threshold)
    adverse_positions = np.flatnonzero(adverse >= threshold)
    first_favorable = int(favorable_positions[0]) if len(favorable_positions) else None
    first_adverse = int(adverse_positions[0]) if len(adverse_positions) else None
    if first_favorable is None and first_adverse is None:
        return "neither"
    if first_adverse is None:
        return "favorable_first"
    if first_favorable is None:
        return "adverse_first"
    if first_favorable < first_adverse:
        return "favorable_first"
    if first_adverse < first_favorable:
        return "adverse_first"
    return "same_bar_ambiguous"


def measure_forward_outcomes(
    events: pd.DataFrame,
    m5: pd.DataFrame,
    config: ProjectConfig,
) -> tuple[pd.DataFrame, pd.DataFrame, list[dict[str, Any]]]:
    """Measure exact-horizon gross mid returns and barrier ordering."""

    bars = m5.sort_values("timestamp", kind="stable").reset_index(drop=True)
    times = pd.to_datetime(bars["timestamp"], utc=True)
    time_values = times.astype("int64").to_numpy()
    time_to_index = {int(value): index for index, value in enumerate(time_values)}
    horizons = config.phase2.outcomes.forward_horizons_minutes
    barrier_horizon = config.phase2.outcomes.barrier_horizon_minutes
    threshold = config.phase2.outcomes.barrier_atr
    outcome_rows: list[dict[str, Any]] = []
    barrier_rows: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []

    for event in events.to_dict("records"):
        decision = pd.Timestamp(event["available_at"])
        entry_position = int(np.searchsorted(time_values, decision.value, side="left"))
        if entry_position >= len(bars):
            continue
        entry_at = pd.Timestamp(times.iloc[entry_position])
        atr = float(event["atr"])
        if not np.isfinite(atr) or atr <= 0:
            failures.append(
                {
                    "invariant": "positive_event_atr",
                    "event_id": event["event_id"],
                }
            )
            continue
        entry = float(bars.iloc[entry_position]["mid_open"])
        is_primary = bool(event["is_primary"])

        for horizon in horizons:
            exit_at = entry_at + pd.Timedelta(horizon, unit="min")
            exit_position = time_to_index.get(exit_at.value)
            if exit_position is None:
                continue
            path = bars.iloc[entry_position:exit_position]
            expected_count = horizon // 5
            if len(path) != expected_count:
                continue
            path_times = pd.to_datetime(path["timestamp"], utc=True)
            if (
                len(path_times) > 1
                and not path_times.diff().iloc[1:].eq(pd.Timedelta(5, unit="min")).all()
            ):
                continue
            exit_price = float(bars.iloc[exit_position]["mid_open"])
            raw_return_atr = (exit_price - entry) / atr
            raw_return_pips = (exit_price - entry) / config.research.instrument.pip_size
            for rule in BASELINE_RULES:
                predicted = event.get(rule)
                emitted = predicted in {"long", "short"}
                sign = 1.0 if predicted == "long" else -1.0
                if emitted:
                    if predicted == "long":
                        favorable = (
                            path["mid_high"].to_numpy(dtype="float64") - entry
                        ) / atr
                        adverse = (
                            entry - path["mid_low"].to_numpy(dtype="float64")
                        ) / atr
                    else:
                        favorable = (
                            entry - path["mid_low"].to_numpy(dtype="float64")
                        ) / atr
                        adverse = (
                            path["mid_high"].to_numpy(dtype="float64") - entry
                        ) / atr
                    signed_return_atr = sign * raw_return_atr
                    signed_return_pips = sign * raw_return_pips
                    mfe = float(max(float(favorable.max()), 0.0))
                    mae = float(max(float(adverse.max()), 0.0))
                else:
                    signed_return_atr = np.nan
                    signed_return_pips = np.nan
                    mfe = np.nan
                    mae = np.nan
                outcome_rows.append(
                    {
                        "event_id": event["event_id"],
                        "primitive": event["primitive"],
                        "opportunity_id": event["opportunity_id"],
                        "session": event["session"],
                        "session_date": event["session_date"],
                        "event_at": event["event_at"],
                        "available_at": decision,
                        "entry_at": entry_at,
                        "exit_at": exit_at,
                        "event_direction": event["direction"],
                        "rule": rule,
                        "predicted_direction": predicted,
                        "emitted_prediction": emitted,
                        "is_primary": is_primary,
                        "horizon_minutes": horizon,
                        "atr": atr,
                        "raw_forward_return_atr": raw_return_atr,
                        "signed_forward_return_atr": signed_return_atr,
                        "signed_forward_return_pips": signed_return_pips,
                        "mfe_atr": mfe,
                        "mae_atr": mae,
                        "context_alignment": event["context_alignment"],
                        "displacement_strength": event["displacement_strength"],
                        "body_atr": event["body_atr"],
                        "path_bar_count": len(path),
                        "event_year": pd.Timestamp(event["event_at"]).year,
                    }
                )
                if horizon == barrier_horizon and emitted:
                    barrier_rows.append(
                        {
                            "event_id": event["event_id"],
                            "primitive": event["primitive"],
                            "opportunity_id": event["opportunity_id"],
                            "session": event["session"],
                            "session_date": event["session_date"],
                            "event_direction": event["direction"],
                            "rule": rule,
                            "predicted_direction": predicted,
                            "is_primary": is_primary,
                            "barrier_atr": threshold,
                            "barrier_horizon_minutes": barrier_horizon,
                            "barrier_sequence": _barrier_label(
                                favorable, adverse, threshold
                            ),
                        }
                    )
    return (
        pd.DataFrame.from_records(outcome_rows),
        pd.DataFrame.from_records(barrier_rows),
        failures,
    )


def _cluster_ci(
    frame: pd.DataFrame,
    *,
    resamples: int,
    confidence_level: float,
    seed: int,
) -> tuple[float | None, float | None]:
    clean = frame.dropna(subset=["signed_forward_return_atr"])
    daily = clean.groupby("session_date")["signed_forward_return_atr"].agg(
        ["sum", "count"]
    )
    if daily.empty:
        return None, None
    rng = np.random.default_rng(seed)
    positions = rng.integers(0, len(daily), size=(resamples, len(daily)))
    estimates = daily["sum"].to_numpy()[positions].sum(axis=1) / daily[
        "count"
    ].to_numpy()[positions].sum(axis=1)
    alpha = 1 - confidence_level
    return (
        float(np.quantile(estimates, alpha / 2)),
        float(np.quantile(estimates, 1 - alpha / 2)),
    )


def summarize_outcomes(
    outcomes: pd.DataFrame,
    config: ProjectConfig,
) -> pd.DataFrame:
    """Summarize registered overall and descriptive strata."""

    rows: list[dict[str, Any]] = []
    samples = (("primary", outcomes[outcomes["is_primary"]]), ("all_events", outcomes))
    scope_columns = {
        "session": "session",
        "direction": "event_direction",
        "event_type": "primitive",
        "context_alignment": "context_alignment",
        "displacement_strength": "displacement_strength",
    }
    for sample_name, sample in samples:
        scoped_frames: list[tuple[str, str, pd.DataFrame]] = [
            ("overall", "all", sample)
        ]
        for scope, column in scope_columns.items():
            scoped_frames.extend(
                (scope, str(value), sample[sample[column].eq(value)])
                for value in sorted(sample[column].dropna().unique())
            )
        for scope, value, scoped in scoped_frames:
            for (primitive, rule, horizon), frame in scoped.groupby(
                ["primitive", "rule", "horizon_minutes"], sort=True
            ):
                emitted = frame[frame["emitted_prediction"]].dropna(
                    subset=["signed_forward_return_atr"]
                )
                ci_lower = None
                ci_upper = None
                if sample_name == "primary" and scope == "overall":
                    ci_lower, ci_upper = _cluster_ci(
                        emitted,
                        resamples=config.phase2.reporting.bootstrap_resamples,
                        confidence_level=config.phase2.reporting.confidence_level,
                        seed=config.phase2.baselines.random_seed,
                    )
                rows.append(
                    {
                        "sample": sample_name,
                        "scope": scope,
                        "value": value,
                        "primitive": primitive,
                        "rule": rule,
                        "horizon_minutes": int(horizon),
                        "event_count": int(frame["event_id"].nunique()),
                        "prediction_count": len(emitted),
                        "prediction_coverage": (
                            len(emitted) / len(frame) if len(frame) else None
                        ),
                        "mean_signed_return_atr": (
                            float(emitted["signed_forward_return_atr"].mean())
                            if len(emitted)
                            else None
                        ),
                        "median_signed_return_atr": (
                            float(emitted["signed_forward_return_atr"].median())
                            if len(emitted)
                            else None
                        ),
                        "positive_return_rate": (
                            float(emitted["signed_forward_return_atr"].gt(0).mean())
                            if len(emitted)
                            else None
                        ),
                        "mean_mfe_atr": (
                            float(emitted["mfe_atr"].mean()) if len(emitted) else None
                        ),
                        "mean_mae_atr": (
                            float(emitted["mae_atr"].mean()) if len(emitted) else None
                        ),
                        "cluster_ci_lower": ci_lower,
                        "cluster_ci_upper": ci_upper,
                    }
                )
    return pd.DataFrame.from_records(rows)


def summarize_barriers(barriers: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for sample_name, sample in (
        ("primary", barriers[barriers["is_primary"]]),
        ("all_events", barriers),
    ):
        for (primitive, rule), frame in sample.groupby(["primitive", "rule"]):
            counts = frame["barrier_sequence"].value_counts()
            favorable = int(counts.get("favorable_first", 0))
            adverse = int(counts.get("adverse_first", 0))
            resolved = favorable + adverse
            rows.append(
                {
                    "sample": sample_name,
                    "primitive": primitive,
                    "rule": rule,
                    "event_count": len(frame),
                    "favorable_first_count": favorable,
                    "adverse_first_count": adverse,
                    "same_bar_ambiguous_count": int(
                        counts.get("same_bar_ambiguous", 0)
                    ),
                    "neither_count": int(counts.get("neither", 0)),
                    "resolved_count": resolved,
                    "favorable_first_rate_resolved": (
                        favorable / resolved if resolved else None
                    ),
                }
            )
    return pd.DataFrame.from_records(rows)


def random_direction_null(
    outcomes: pd.DataFrame,
    config: ProjectConfig,
) -> pd.DataFrame:
    primary_horizon = config.phase2.outcomes.primary_horizon_minutes
    base = outcomes[
        outcomes["is_primary"]
        & outcomes["rule"].eq("event_direction")
        & outcomes["horizon_minutes"].eq(primary_horizon)
    ]
    rng = np.random.default_rng(config.phase2.baselines.random_seed)
    resamples = config.phase2.baselines.random_null_resamples
    rows: list[dict[str, Any]] = []
    for primitive in PRIMITIVES:
        frame = base[base["primitive"].eq(primitive)]
        raw = frame["raw_forward_return_atr"].to_numpy(dtype="float64")
        if not len(raw):
            continue
        signs = rng.choice(np.array([-1.0, 1.0]), size=(resamples, len(raw)))
        estimates = (signs * raw).mean(axis=1)
        rows.append(
            {
                "primitive": primitive,
                "horizon_minutes": primary_horizon,
                "event_count": len(raw),
                "resamples": resamples,
                "null_mean": float(estimates.mean()),
                "null_p025": float(np.quantile(estimates, 0.025)),
                "null_p975": float(np.quantile(estimates, 0.975)),
            }
        )
    return pd.DataFrame.from_records(rows)


def paired_baseline_comparisons(
    outcomes: pd.DataFrame,
    config: ProjectConfig,
) -> pd.DataFrame:
    primary = outcomes[
        outcomes["is_primary"]
        & outcomes["horizon_minutes"].eq(config.phase2.outcomes.primary_horizon_minutes)
    ]
    pivot = primary.pivot_table(
        index=["primitive", "event_id"],
        columns="rule",
        values="signed_forward_return_atr",
        aggfunc="first",
    )
    rows: list[dict[str, Any]] = []
    for primitive in PRIMITIVES:
        frame = pivot.loc[primitive] if primitive in pivot.index else pd.DataFrame()
        if isinstance(frame, pd.Series):
            frame = frame.to_frame().T
        for baseline in (
            "session_momentum",
            "session_mean_reversion",
            "four_bar_close_breakout",
        ):
            if frame.empty or baseline not in frame or "event_direction" not in frame:
                continue
            paired = frame[["event_direction", baseline]].dropna()
            difference = paired["event_direction"] - paired[baseline]
            rows.append(
                {
                    "primitive": primitive,
                    "baseline": baseline,
                    "paired_count": len(paired),
                    "event_mean_atr": (
                        float(paired["event_direction"].mean()) if len(paired) else None
                    ),
                    "baseline_mean_atr": (
                        float(paired[baseline].mean()) if len(paired) else None
                    ),
                    "mean_paired_increment_atr": (
                        float(difference.mean()) if len(paired) else None
                    ),
                }
            )
    return pd.DataFrame.from_records(rows)


def _invariant_failures(
    events: pd.DataFrame,
    primary: pd.DataFrame,
    outcomes: pd.DataFrame,
    measurement_failures: list[dict[str, Any]],
    config: ProjectConfig,
) -> list[dict[str, Any]]:
    failures = list(measurement_failures)

    def add(name: str, count: int) -> None:
        if count:
            failures.append({"invariant": name, "failure_count": int(count)})

    year = config.phase2.scope.construction_year
    add(
        "event_year_is_construction",
        int(pd.to_datetime(events["event_at"]).dt.year.ne(year).sum()),
    )
    add("positive_event_atr", int(events["atr"].le(0).sum()))
    add(
        "event_available_after_bar_start",
        int(events["available_at"].le(events["event_at"]).sum()),
    )
    sweep = events[events["primitive"].eq("liquidity_sweep")]
    add(
        "sweep_source_available_by_event_bar_start",
        int(sweep["source_swing_available_at"].gt(sweep["event_at"]).sum()),
    )
    add(
        "one_primary_event_per_primitive_session",
        int(primary.duplicated(["primitive", "opportunity_id"], keep=False).sum()),
    )
    add("outcome_year_is_construction", int(outcomes["event_year"].ne(year).sum()))
    add(
        "entry_not_before_availability",
        int(outcomes["entry_at"].lt(outcomes["available_at"]).sum()),
    )
    add(
        "exact_horizon_exit",
        int(
            ((outcomes["exit_at"] - outcomes["entry_at"]).dt.total_seconds() / 60)
            .ne(outcomes["horizon_minutes"])
            .sum()
        ),
    )
    add("positive_outcome_atr", int(outcomes["atr"].le(0).sum()))
    add(
        "baseline_available_by_event_decision",
        int(events["baseline_feature_available_at"].gt(events["available_at"]).sum()),
    )
    primary_keys = set(primary["event_id"])
    all_keys = set(events["event_id"])
    add("primary_subset_of_all_events", len(primary_keys - all_keys))
    return failures


def evaluate_gates(
    metrics: pd.DataFrame,
    barriers: pd.DataFrame,
    random_null: pd.DataFrame,
    paired: pd.DataFrame,
    failures: list[dict[str, Any]],
    config: ProjectConfig,
) -> dict[str, Any]:
    settings = config.phase2.decision_gate
    primary_horizon = config.phase2.outcomes.primary_horizon_minutes
    gates: dict[str, Any] = {}
    for primitive in PRIMITIVES:
        overall = metrics[
            metrics["sample"].eq("primary")
            & metrics["scope"].eq("overall")
            & metrics["primitive"].eq(primitive)
            & metrics["rule"].eq("event_direction")
        ]
        primary = overall[overall["horizon_minutes"].eq(primary_horizon)]
        if primary.empty:
            gates[primitive] = {
                "passed": False,
                "checks": {"has_primary_metrics": False},
            }
            continue
        row = primary.iloc[0]
        null_row = random_null[random_null["primitive"].eq(primitive)]
        barrier_row = barriers[
            barriers["sample"].eq("primary")
            & barriers["primitive"].eq(primitive)
            & barriers["rule"].eq("event_direction")
        ]
        scope = metrics[
            metrics["sample"].eq("primary")
            & metrics["primitive"].eq(primitive)
            & metrics["rule"].eq("event_direction")
            & metrics["horizon_minutes"].eq(primary_horizon)
        ]
        session_rows = scope[scope["scope"].eq("session")].set_index("value")
        direction_rows = scope[scope["scope"].eq("direction")].set_index("value")
        paired_rows = paired[paired["primitive"].eq(primitive)].set_index("baseline")
        positive_horizons = int(overall["mean_signed_return_atr"].gt(0).sum())

        def robust_scope(rows: pd.DataFrame, values: tuple[str, ...]) -> bool:
            return all(
                value in rows.index
                and int(rows.loc[value, "prediction_count"])
                >= config.phase2.reporting.minimum_scope_events
                and float(rows.loc[value, "mean_signed_return_atr"]) > 0
                for value in values
            )

        favorable_rate = (
            None
            if barrier_row.empty
            else barrier_row.iloc[0]["favorable_first_rate_resolved"]
        )
        checks = {
            "zero_invariant_failures": not failures,
            "minimum_primary_events": int(row["prediction_count"])
            >= settings.minimum_primary_events,
            "positive_primary_mean": float(row["mean_signed_return_atr"]) > 0,
            "primary_cluster_ci_lower_above_zero": (
                row["cluster_ci_lower"] is not None
                and float(row["cluster_ci_lower"]) > 0
            ),
            "above_random_null_upper": (
                not null_row.empty
                and float(row["mean_signed_return_atr"])
                > float(null_row.iloc[0]["null_p975"])
            ),
            "favorable_first_rate_above_half": (
                favorable_rate is not None and float(favorable_rate) > 0.5
            ),
            "positive_each_session": robust_scope(session_rows, ("london", "new_york")),
            "positive_each_direction": robust_scope(direction_rows, ("long", "short")),
            "minimum_positive_horizons": positive_horizons
            >= settings.minimum_positive_horizons,
            "positive_increment_vs_session_momentum": (
                "session_momentum" in paired_rows.index
                and float(
                    paired_rows.loc["session_momentum", "mean_paired_increment_atr"]
                )
                > 0
            ),
            "positive_increment_vs_session_mean_reversion": (
                "session_mean_reversion" in paired_rows.index
                and float(
                    paired_rows.loc[
                        "session_mean_reversion", "mean_paired_increment_atr"
                    ]
                )
                > 0
            ),
        }
        gates[primitive] = {
            "passed": all(checks.values()),
            "checks": checks,
            "primary_event_count": int(row["prediction_count"]),
            "primary_mean_signed_return_atr": float(row["mean_signed_return_atr"]),
            "primary_cluster_ci": [
                row["cluster_ci_lower"],
                row["cluster_ci_upper"],
            ],
            "positive_horizon_count": positive_horizons,
            "favorable_first_rate_resolved": favorable_rate,
        }
    return gates


def run_phase2_directional_audit(
    project_root: Path,
    data_root: Path,
    *,
    artifact_root: Path | None = None,
) -> Phase2Result:
    """Run the preregistered 2024-only directional primitive audit."""

    config = load_project_config(project_root / "config")
    m5, input_paths = _load_construction_m5(data_root, config)
    fingerprint, input_hashes = _fingerprint(project_root, input_paths)
    output = (
        artifact_root or project_root / "artifacts" / "phase2" / "construction"
    ) / fingerprint
    output.mkdir(parents=True, exist_ok=True)

    bars = _prepare_bars(m5, config)
    swings: dict[str, pd.DataFrame] = {}
    contexts: dict[str, pd.DataFrame] = {}
    breaks: dict[str, pd.DataFrame] = {}
    for timeframe in ("15min", "1H", "4H"):
        swings[timeframe] = label_swings(
            bars[timeframe],
            config.structure,
            pip_size=config.research.instrument.pip_size,
        )
        breaks[timeframe], contexts[timeframe] = label_structure_state_machine(
            bars[timeframe],
            swings[timeframe],
            config.structure,
            pip_size=config.research.instrument.pip_size,
        )

    sweep_events, sweep_stats = label_liquidity_sweeps(
        bars["15min"],
        swings["15min"],
        minimum_excursion_atr=(
            config.phase2.events.liquidity_sweep_minimum_excursion_atr
        ),
    )
    displacement_events = label_displacements(
        bars["15min"],
        minimum_body_atr=config.phase2.events.displacement_minimum_body_atr,
    )
    primitive_events = pd.concat(
        [
            frame.dropna(axis=1, how="all")
            for frame in (
                _break_events(breaks["15min"]),
                sweep_events,
                displacement_events,
            )
        ],
        ignore_index=True,
        sort=False,
    )
    opportunities = build_full_session_opportunities(m5, config)
    opportunities = opportunities[opportunities["year"].eq(2024)].reset_index(drop=True)
    events = assign_events_to_sessions(primitive_events, opportunities)
    events = attach_event_features(events, m5, bars["15min"], contexts, config)
    primary = select_primary_events(events)
    primary_keys = set(primary["event_id"])
    events["is_primary"] = events["event_id"].isin(primary_keys)
    primary = events[events["is_primary"]].copy().reset_index(drop=True)

    outcomes, barrier_paths, measurement_failures = measure_forward_outcomes(
        events, m5, config
    )
    metrics = summarize_outcomes(outcomes, config)
    barrier_summary = summarize_barriers(barrier_paths)
    random_null = random_direction_null(outcomes, config)
    paired = paired_baseline_comparisons(outcomes, config)
    failures = _invariant_failures(
        events, primary, outcomes, measurement_failures, config
    )
    gates = evaluate_gates(
        metrics, barrier_summary, random_null, paired, failures, config
    )
    qualified = [primitive for primitive, gate in gates.items() if gate["passed"]]
    winner = None
    if qualified:
        winner = max(
            qualified,
            key=lambda primitive: gates[primitive]["primary_cluster_ci"][0],
        )

    primary_horizon = config.phase2.outcomes.primary_horizon_minutes
    primary_overall = metrics[
        metrics["sample"].eq("primary")
        & metrics["scope"].eq("overall")
        & metrics["rule"].eq("event_direction")
        & metrics["horizon_minutes"].eq(primary_horizon)
    ]
    summary = {
        "phase": config.phase2.phase,
        "fingerprint": fingerprint,
        "config_status": config.phase2.status,
        "construction_year": config.phase2.scope.construction_year,
        "historical_replication_year_accessed": False,
        "historical_replication_is_pristine_holdout": False,
        "transaction_costs_applied": False,
        "m5_bar_count": len(m5),
        "session_opportunity_count": len(opportunities),
        "all_event_counts": {
            primitive: int(events["primitive"].eq(primitive).sum())
            for primitive in PRIMITIVES
        },
        "primary_event_counts": {
            primitive: int(primary["primitive"].eq(primitive).sum())
            for primitive in PRIMITIVES
        },
        "sweep_label_audit": sweep_stats,
        "primary_60m_event_direction": {
            row["primitive"]: {
                "event_count": int(row["prediction_count"]),
                "mean_signed_return_atr": row["mean_signed_return_atr"],
                "positive_return_rate": row["positive_return_rate"],
                "cluster_ci": [row["cluster_ci_lower"], row["cluster_ci_upper"]],
            }
            for row in primary_overall.to_dict("records")
        },
        "invariant_failure_count": len(failures),
        "invariant_failures": failures,
        "primitive_gates": gates,
        "qualified_primitives": qualified,
        "recommended_winner": winner,
        "historical_replication_permitted": bool(winner and not failures),
        "decision": (
            "freeze_winner_before_historical_replication"
            if winner and not failures
            else "close_current_structure_signal_thesis"
        ),
    }

    events.to_parquet(output / "events-all.parquet", index=False)
    primary.to_parquet(output / "events-primary.parquet", index=False)
    outcomes.to_parquet(output / "forward-outcomes.parquet", index=False)
    barrier_paths.to_parquet(output / "barrier-paths.parquet", index=False)
    metrics.to_csv(output / "metrics.csv", index=False)
    barrier_summary.to_csv(output / "barrier-summary.csv", index=False)
    random_null.to_csv(output / "random-null.csv", index=False)
    paired.to_csv(output / "paired-baselines.csv", index=False)
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True, default=_json_default) + "\n",
        encoding="utf-8",
    )
    manifest = {
        "phase": config.phase2.phase,
        "fingerprint": fingerprint,
        "created_at": datetime.now(UTC).isoformat(),
        "input_hashes": input_hashes,
        "historical_replication_files_opened": False,
        "artifact_files": sorted(path.name for path in output.iterdir()),
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return Phase2Result(artifact_directory=output, summary=summary)
