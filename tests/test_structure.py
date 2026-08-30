from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

from gbpusd_structure.config import load_project_config
from gbpusd_structure.structure import (
    add_atr,
    build_support_resistance_zones,
    label_fair_value_gaps,
    label_structure_breaks,
    label_swings,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG = load_project_config(PROJECT_ROOT / "config").structure


def structure_bars(
    highs: list[float],
    lows: list[float],
    *,
    opens: list[float] | None = None,
    closes: list[float] | None = None,
    timeframe: str = "1H",
) -> pd.DataFrame:
    count = len(highs)
    start = datetime(2024, 1, 2, tzinfo=UTC)
    timestamps = pd.to_datetime(
        [start + timedelta(hours=index) for index in range(count)], utc=True
    )
    if opens is None:
        opens = [(high + low) / 2 for high, low in zip(highs, lows, strict=True)]
    if closes is None:
        closes = opens
    frame = pd.DataFrame(
        {
            "bar_id": [f"{timeframe}:{value.isoformat()}" for value in timestamps],
            "timeframe": timeframe,
            "timestamp": timestamps,
            "available_at": timestamps + pd.Timedelta(1, unit="h"),
            "mid_open": opens,
            "mid_high": highs,
            "mid_low": lows,
            "mid_close": closes,
            "coverage_ratio": 1.0,
            "atr": 0.001,
            "body_atr": [
                abs(close - open_) / 0.001
                for open_, close in zip(opens, closes, strict=True)
            ],
            "structure_eligible": True,
        }
    )
    return frame


def test_atr_uses_only_current_and_prior_completed_bars() -> None:
    bars = structure_bars(
        [1.1010, 1.1020, 1.1030, 1.1040],
        [1.0990, 1.1000, 1.1010, 1.1020],
        closes=[1.1000, 1.1010, 1.1020, 1.1030],
    )
    result = add_atr(bars, period=3)

    assert result.loc[:1, "atr"].isna().all()
    assert result.loc[2, "atr"] == pytest.approx(0.002)
    changed_future = bars.copy()
    changed_future.loc[3, "mid_high"] = 1.5000
    changed = add_atr(changed_future, period=3)
    assert changed.loc[2, "atr"] == result.loc[2, "atr"]


def test_swing_is_available_only_after_right_side_confirmation() -> None:
    bars = structure_bars(
        [1.1000, 1.1010, 1.1050, 1.1020, 1.1010],
        [1.0980, 1.0990, 1.1000, 1.0995, 1.0985],
    )
    swings = label_swings(bars, CONFIG, pip_size=0.0001)
    pivot = swings[
        (swings["event_type"] == "swing_high") & (swings["pivot_index"] == 2)
    ].iloc[0]

    assert pivot["ambiguous_equal"] == False  # noqa: E712
    assert pivot["confirmation_index"] == 4
    assert pivot["event_at"] == bars.loc[2, "timestamp"]
    assert pivot["available_at"] == bars.loc[4, "available_at"]
    assert pivot["available_at"] > pivot["event_at"]


def test_near_equal_swing_is_explicitly_ambiguous() -> None:
    bars = structure_bars(
        [1.1000, 1.1010, 1.10105, 1.1005, 1.1000],
        [1.0980, 1.0985, 1.0990, 1.0987, 1.0982],
    )
    swings = label_swings(bars, CONFIG, pip_size=0.0001)
    pivot = swings[
        (swings["event_type"] == "swing_high") & (swings["pivot_index"] == 2)
    ].iloc[0]

    assert bool(pivot["ambiguous_equal"])
    assert pivot["extreme_margin_pips"] == pytest.approx(0.5)


def test_breaks_distinguish_bos_and_choch_from_prior_regime() -> None:
    bars = structure_bars(
        [1.08, 1.09, 1.13, 1.07],
        [1.03, 1.04, 1.08, 0.98],
        opens=[1.05, 1.06, 1.08, 1.06],
        closes=[1.05, 1.06, 1.12, 0.99],
    )
    swings = pd.DataFrame(
        [
            {
                "event_id": "h1",
                "event_type": "swing_high",
                "confirmation_index": 0,
                "ambiguous_equal": False,
                "price": 1.08,
                "bar_id": "h1",
            },
            {
                "event_id": "l1",
                "event_type": "swing_low",
                "confirmation_index": 0,
                "ambiguous_equal": False,
                "price": 1.03,
                "bar_id": "l1",
            },
            {
                "event_id": "h2",
                "event_type": "swing_high",
                "confirmation_index": 1,
                "ambiguous_equal": False,
                "price": 1.09,
                "bar_id": "h2",
            },
            {
                "event_id": "l2",
                "event_type": "swing_low",
                "confirmation_index": 1,
                "ambiguous_equal": False,
                "price": 1.04,
                "bar_id": "l2",
            },
        ]
    )
    events = label_structure_breaks(
        bars,
        swings,
        CONFIG,
        pip_size=0.0001,
        break_buffer_atr=0,
    )

    assert events[["event_type", "direction"]].values.tolist() == [
        ["bos", "up"],
        ["choch", "down"],
    ]
    assert (events["available_at"] > events["event_at"]).all()


def test_fvg_records_point_in_time_creation_and_later_full_fill() -> None:
    bars = structure_bars(
        [1.1000, 1.1010, 1.1030, 1.1020, 1.1010],
        [1.0990, 1.0995, 1.1010, 1.1005, 1.0990],
    )
    events = label_fair_value_gaps(bars, CONFIG, minimum_size_atr=0)
    event = events[
        (events["direction"] == "up") & (events["event_at"] == bars.loc[2, "timestamp"])
    ].iloc[0]

    assert event["lower_bound"] == pytest.approx(1.1000)
    assert event["upper_bound"] == pytest.approx(1.1010)
    assert event["available_at"] == bars.loc[2, "available_at"]
    assert event["partial_fill_at"] == bars.loc[3, "available_at"]
    assert event["full_fill_at"] == bars.loc[4, "available_at"]
    assert event["status"] == "filled"


def test_sr_zone_becomes_active_only_after_second_confirmed_touch() -> None:
    bars = structure_bars([1.11] * 10, [1.09] * 10)
    swings = pd.DataFrame(
        [
            {
                "event_id": "h1",
                "event_type": "swing_high",
                "event_at": bars.loc[1, "timestamp"],
                "available_at": bars.loc[2, "available_at"],
                "direction": "up",
                "price": 1.1000,
                "atr": 0.001,
                "ambiguous_equal": False,
                "confirmation_index": 2,
                "bar_id": "h1",
            },
            {
                "event_id": "h2",
                "event_type": "swing_high",
                "event_at": bars.loc[4, "timestamp"],
                "available_at": bars.loc[5, "available_at"],
                "direction": "up",
                "price": 1.1001,
                "atr": 0.001,
                "ambiguous_equal": False,
                "confirmation_index": 5,
                "bar_id": "h2",
            },
        ]
    )
    zones, snapshots = build_support_resistance_zones(swings, bars, CONFIG)

    assert len(zones) == 1
    assert zones.loc[0, "touch_count"] == 2
    assert zones.loc[0, "active_at"] == swings.loc[1, "available_at"]
    assert zones.loc[0, "age_bars_at_sample_end"] == 7
    assert zones.loc[0, "bars_since_last_touch"] == 4
    assert snapshots["active"].tolist() == [False, True]
