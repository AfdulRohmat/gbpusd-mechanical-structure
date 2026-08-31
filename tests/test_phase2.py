from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from gbpusd_structure.config import load_project_config
from gbpusd_structure.phase2 import (
    _barrier_label,
    label_displacements,
    label_liquidity_sweeps,
    measure_forward_outcomes,
    select_primary_events,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _bar(
    timestamp: str,
    *,
    open_: float,
    high: float,
    low: float,
    close: float,
    atr: float = 0.01,
) -> dict[str, object]:
    start = pd.Timestamp(timestamp)
    return {
        "bar_id": f"15min:{start.isoformat()}",
        "timestamp": start,
        "available_at": start + pd.Timedelta(15, unit="min"),
        "mid_open": open_,
        "mid_high": high,
        "mid_low": low,
        "mid_close": close,
        "atr": atr,
        "body_atr": abs(close - open_) / atr,
        "structure_eligible": True,
    }


def _swing(
    kind: str,
    price: float,
    available_at: str,
    suffix: str,
) -> dict[str, object]:
    timestamp = pd.Timestamp(available_at)
    return {
        "event_id": f"swing:{suffix}",
        "event_type": f"swing_{kind}",
        "price": price,
        "available_at": timestamp,
    }


def test_liquidity_sweep_requires_source_known_at_bar_start_and_consumes_it() -> None:
    bars = pd.DataFrame(
        [
            _bar(
                "2024-01-02 08:00:00+00:00",
                open_=0.99,
                high=1.011,
                low=0.98,
                close=0.995,
            ),
            _bar(
                "2024-01-02 08:15:00+00:00",
                open_=0.995,
                high=1.02,
                low=0.99,
                close=0.996,
            ),
        ]
    )
    swings = pd.DataFrame([_swing("high", 1.0, "2024-01-02 08:00:00+00:00", "high")])

    events, stats = label_liquidity_sweeps(bars, swings, minimum_excursion_atr=0.05)

    assert len(events) == 1
    assert events.iloc[0]["event_at"] == pd.Timestamp("2024-01-02 08:00:00+00:00")
    assert events.iloc[0]["direction"] == "short"
    assert stats["high_excursions"] == 1


def test_two_sided_sweep_is_excluded_as_ambiguous() -> None:
    bars = pd.DataFrame(
        [
            _bar(
                "2024-01-02 08:00:00+00:00",
                open_=1.0,
                high=1.02,
                low=0.98,
                close=1.0,
            )
        ]
    )
    swings = pd.DataFrame(
        [
            _swing("high", 1.01, "2024-01-02 08:00:00+00:00", "high"),
            _swing("low", 0.99, "2024-01-02 08:00:00+00:00", "low"),
        ]
    )

    events, stats = label_liquidity_sweeps(bars, swings, minimum_excursion_atr=0.05)

    assert events.empty
    assert stats["ambiguous_bars"] == 1


def test_displacement_uses_completed_body_direction() -> None:
    bars = pd.DataFrame(
        [
            _bar(
                "2024-01-02 08:00:00+00:00",
                open_=1.0,
                high=1.02,
                low=0.99,
                close=1.009,
            ),
            _bar(
                "2024-01-02 08:15:00+00:00",
                open_=1.01,
                high=1.02,
                low=0.99,
                close=1.005,
            ),
        ]
    )

    events = label_displacements(bars, minimum_body_atr=0.8)

    assert len(events) == 1
    assert events.iloc[0]["direction"] == "long"
    assert events.iloc[0]["body_atr"] == pytest.approx(0.9)


def test_primary_selection_keeps_first_primitive_event_per_session() -> None:
    events = pd.DataFrame(
        [
            {
                "event_id": "later",
                "primitive": "bos",
                "opportunity_id": "day:london",
                "available_at": pd.Timestamp("2024-01-02 09:00:00+00:00"),
            },
            {
                "event_id": "first",
                "primitive": "bos",
                "opportunity_id": "day:london",
                "available_at": pd.Timestamp("2024-01-02 08:30:00+00:00"),
            },
            {
                "event_id": "sweep",
                "primitive": "liquidity_sweep",
                "opportunity_id": "day:london",
                "available_at": pd.Timestamp("2024-01-02 08:45:00+00:00"),
            },
        ]
    )

    selected = select_primary_events(events)

    assert set(selected["event_id"]) == {"first", "sweep"}


def test_barrier_label_preserves_same_bar_ambiguity() -> None:
    favorable = pd.Series([0.2, 1.1]).to_numpy()
    adverse = pd.Series([0.3, 1.2]).to_numpy()

    assert _barrier_label(favorable, adverse, 1.0) == "same_bar_ambiguous"


def test_forward_horizon_starts_at_first_m5_after_event_availability() -> None:
    config = load_project_config(PROJECT_ROOT / "config")
    timestamps = pd.date_range(
        "2024-01-02 08:05:00+00:00",
        periods=49,
        freq="5min",
    )
    m5 = pd.DataFrame(
        {
            "timestamp": timestamps,
            "mid_open": [1.2 + index * 0.0001 for index in range(49)],
            "mid_high": [1.2001 + index * 0.0001 for index in range(49)],
            "mid_low": [1.1999 + index * 0.0001 for index in range(49)],
        }
    )
    event = {
        "event_id": "delayed-entry",
        "primitive": "bos",
        "opportunity_id": "2024-01-02:london",
        "session": "london",
        "session_date": "2024-01-02",
        "event_at": pd.Timestamp("2024-01-02 07:45:00+00:00"),
        "available_at": pd.Timestamp("2024-01-02 08:00:00+00:00"),
        "direction": "long",
        "event_direction": "long",
        "seeded_random_direction": "short",
        "session_momentum": "long",
        "session_mean_reversion": "short",
        "four_bar_close_breakout": None,
        "atr": 0.001,
        "body_atr": 1.0,
        "context_alignment": "both_aligned",
        "displacement_strength": "0_8_to_1_2",
        "is_primary": True,
    }

    outcomes, _, failures = measure_forward_outcomes(pd.DataFrame([event]), m5, config)

    first = outcomes[outcomes["horizon_minutes"].eq(15)].iloc[0]
    assert failures == []
    assert first["entry_at"] == pd.Timestamp("2024-01-02 08:05:00+00:00")
    assert first["exit_at"] == pd.Timestamp("2024-01-02 08:20:00+00:00")


def test_phase2_configuration_is_construction_only() -> None:
    config = load_project_config(PROJECT_ROOT / "config")

    assert config.phase2.scope.construction_year == 2024
    assert config.phase2.scope.historical_replication_access_allowed is False
