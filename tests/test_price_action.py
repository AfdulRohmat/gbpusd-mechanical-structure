from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from gbpusd_structure.config import load_project_config
from gbpusd_structure.price_action import (
    adjacent_overlap_ratio,
    build_m15_price_action_states,
    congestion_status,
    signal_bar_quality,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _config():
    return load_project_config(PROJECT_ROOT / "config")


def test_signal_bar_quality_is_directional_and_rejects_doji() -> None:
    bullish = {
        "mid_open": 0.998,
        "mid_high": 1.01,
        "mid_low": 0.99,
        "mid_close": 1.008,
        "atr": 0.02,
    }
    doji = {**bullish, "mid_close": 0.999}

    long_pass, metrics = signal_bar_quality(bullish, "long", _config())
    short_pass, _ = signal_bar_quality(bullish, "short", _config())
    doji_pass, _ = signal_bar_quality(doji, "long", _config())

    assert long_pass
    assert not short_pass
    assert not doji_pass
    assert metrics["close_location"] == 0.9


def test_adjacent_overlap_uses_smaller_bar_range() -> None:
    first = pd.Series({"mid_high": 10.0, "mid_low": 0.0})
    second = pd.Series({"mid_high": 8.0, "mid_low": 3.0})

    assert adjacent_overlap_ratio(first, second) == 1.0


def test_congestion_requires_both_small_range_and_overlap() -> None:
    bars = pd.DataFrame(
        {
            "mid_high": [1.0010, 1.0011, 1.0010, 1.0011, 1.0010, 1.0011],
            "mid_low": [1.0000, 1.0001, 1.0000, 1.0001, 1.0000, 1.0001],
            "atr": [0.001] * 6,
        }
    )

    veto, total_range, overlap = congestion_status(bars, 5, _config())

    assert veto
    assert total_range == pytest.approx(1.1)
    assert overlap is not None and overlap > 0.8


def _m15_bars(count: int) -> pd.DataFrame:
    timestamps = pd.date_range(
        "2024-01-02 00:00:00+00:00",
        periods=count,
        freq="15min",
    )
    return pd.DataFrame(
        {
            "bar_id": [f"15min:{value.isoformat()}" for value in timestamps],
            "timestamp": timestamps,
            "available_at": timestamps + pd.Timedelta(15, unit="min"),
            "mid_open": [1.0] * count,
            "mid_high": [1.01] * count,
            "mid_low": [0.99] * count,
            "mid_close": [1.0] * count,
            "atr": [0.01] * count,
            "structure_eligible": [True] * count,
        }
    )


def _swing(
    bars: pd.DataFrame,
    *,
    kind: str,
    pivot_index: int,
    available_index: int,
    price: float,
    relationship: str,
) -> dict[str, object]:
    return {
        "event_id": f"swing:{kind}:{pivot_index}",
        "event_type": f"swing_{kind}",
        "pivot_index": pivot_index,
        "available_at": bars.iloc[available_index]["available_at"],
        "price": price,
        "structural_relationship": relationship,
    }


def test_trendline_break_waits_for_final_extreme() -> None:
    bars = _m15_bars(8)
    bars.loc[5, ["mid_high", "mid_close"]] = [1.04, 1.03]
    bars.loc[6, ["mid_high", "mid_close"]] = [1.03, 1.01]
    bars.loc[7, ["mid_high", "mid_close"]] = [1.0395, 1.02]
    swings = pd.DataFrame(
        [
            _swing(
                bars,
                kind="high",
                pivot_index=0,
                available_index=1,
                price=1.02,
                relationship="H0",
            ),
            _swing(
                bars,
                kind="low",
                pivot_index=1,
                available_index=2,
                price=1.00,
                relationship="L0",
            ),
            _swing(
                bars,
                kind="high",
                pivot_index=2,
                available_index=3,
                price=1.03,
                relationship="HH",
            ),
            _swing(
                bars,
                kind="low",
                pivot_index=3,
                available_index=4,
                price=1.01,
                relationship="HL",
            ),
        ]
    )

    states, transitions, _ = build_m15_price_action_states(bars, swings, _config())

    assert states.iloc[4]["state"] == "trend_up_active"
    assert states.iloc[6]["state"] == "trend_up_break_pending_extreme"
    assert states.iloc[7]["state"] == "post_up_extreme_transition"
    assert "uptrendline_close_break" in set(transitions["cause"])
    assert "up_final_extreme_fulfilled" in set(transitions["cause"])


def test_range_break_acceptance_requires_retest_hold() -> None:
    bars = _m15_bars(23)
    bars.loc[20, ["mid_high", "mid_low", "mid_close"]] = [
        1.012,
        1.009,
        1.011,
    ]
    bars.loc[21, ["mid_high", "mid_low", "mid_close"]] = [
        1.013,
        1.0105,
        1.012,
    ]
    bars.loc[22, ["mid_high", "mid_low", "mid_close"]] = [
        1.012,
        1.0095,
        1.011,
    ]
    swings = pd.DataFrame(
        [
            _swing(
                bars,
                kind="high",
                pivot_index=4,
                available_index=6,
                price=1.0100,
                relationship="H0",
            ),
            _swing(
                bars,
                kind="low",
                pivot_index=7,
                available_index=9,
                price=0.9900,
                relationship="L0",
            ),
            _swing(
                bars,
                kind="high",
                pivot_index=11,
                available_index=13,
                price=1.0105,
                relationship="EQH",
            ),
            _swing(
                bars,
                kind="low",
                pivot_index=15,
                available_index=17,
                price=0.9905,
                relationship="EQL",
            ),
        ]
    )

    states, _, events = build_m15_price_action_states(bars, swings, _config())

    assert states.iloc[19]["state"] == "range"
    assert states.iloc[20]["state"] == "range_break_up_pending"
    assert states.iloc[21]["state"] == "range_break_up_wait_retest"
    assert states.iloc[22]["state"] == "trend_up_active"
    assert len(events) == 1
    assert events.iloc[0]["event_type"] == "accepted_breakout_pullback"
