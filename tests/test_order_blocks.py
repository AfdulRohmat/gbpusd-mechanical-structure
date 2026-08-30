from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

from gbpusd_structure.config import load_project_config
from gbpusd_structure.order_blocks import label_order_blocks
from gbpusd_structure.phase0 import _interval_iou

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG = load_project_config(PROJECT_ROOT / "config").structure


def sample_bars(timeframe: str = "1H") -> pd.DataFrame:
    start = datetime(2024, 1, 2, tzinfo=UTC)
    timestamps = pd.to_datetime(
        [start + timedelta(hours=index) for index in range(7)], utc=True
    )
    opens = [1.09, 1.09, 1.10, 1.09, 1.12, 1.10, 1.10]
    closes = [1.09, 1.10, 1.09, 1.13, 1.11, 1.09, 1.10]
    highs = [1.10, 1.11, 1.11, 1.14, 1.12, 1.105, 1.11]
    lows = [1.08, 1.08, 1.08, 1.09, 1.095, 1.079, 1.09]
    return pd.DataFrame(
        {
            "bar_id": [f"{timeframe}:{value.isoformat()}" for value in timestamps],
            "timeframe": timeframe,
            "timestamp": timestamps,
            "available_at": timestamps + pd.Timedelta(1, unit="h"),
            "mid_open": opens,
            "mid_high": highs,
            "mid_low": lows,
            "mid_close": closes,
            "structure_eligible": True,
        }
    )


def anchor(bars: pd.DataFrame, index: int, direction: str = "up") -> dict:
    return {
        "event_id": f"break-{index}",
        "event_type": "bos",
        "event_at": bars.loc[index, "timestamp"],
        "available_at": bars.loc[index, "available_at"],
        "direction": direction,
        "displacement_qualified": True,
        "bar_id": bars.loc[index, "bar_id"],
    }


def test_bullish_order_block_is_available_at_break_and_tracks_lifecycle() -> None:
    bars = sample_bars()
    zones, diagnostics = label_order_blocks(
        bars,
        pd.DataFrame([anchor(bars, 3)]),
        pd.DataFrame(),
        CONFIG,
        pip_size=0.0001,
    )
    zone = zones.iloc[0]

    assert diagnostics.loc[0, "status"] == "created"
    assert zone["candidate_bar_id"] == bars.loc[2, "bar_id"]
    assert zone["candidate_at"] == bars.loc[2, "timestamp"]
    assert zone["available_at"] == bars.loc[3, "available_at"]
    assert zone["available_at"] > zone["candidate_available_at"]
    assert zone["lower_bound"] == pytest.approx(1.08)
    assert zone["upper_bound"] == pytest.approx(1.11)
    assert zone["first_touch_at"] == bars.loc[4, "available_at"]
    assert zone["midpoint_touch_at"] == bars.loc[4, "available_at"]
    assert zone["full_mitigation_at"] == bars.loc[5, "available_at"]
    assert zone["status"] == "fully_mitigated"


def test_close_invalidation_wins_when_full_mitigation_is_same_bar() -> None:
    bars = sample_bars()
    bars.loc[5, "mid_close"] = 1.079
    zones, _ = label_order_blocks(
        bars,
        pd.DataFrame([anchor(bars, 3)]),
        pd.DataFrame(),
        CONFIG,
        pip_size=0.0001,
    )
    zone = zones.iloc[0]

    assert zone["full_mitigation_at"] == bars.loc[5, "available_at"]
    assert zone["invalidation_at"] == bars.loc[5, "available_at"]
    assert zone["status"] == "invalidated"


def test_duplicate_candidate_is_audited_without_second_zone() -> None:
    bars = sample_bars()
    breaks = pd.DataFrame([anchor(bars, 3), anchor(bars, 4)])
    zones, diagnostics = label_order_blocks(
        bars,
        breaks,
        pd.DataFrame(),
        CONFIG,
        pip_size=0.0001,
    )

    assert len(zones) == 1
    assert diagnostics["status"].tolist() == ["created", "duplicate_candidate"]
    assert diagnostics["candidate_found"].all()


def test_missing_opposing_candle_and_daily_scope_are_explicit() -> None:
    bars = sample_bars()
    _, diagnostics = label_order_blocks(
        bars,
        pd.DataFrame([anchor(bars, 3, direction="down")]),
        pd.DataFrame(),
        CONFIG,
        pip_size=0.0001,
        candidate_lookback_bars=1,
    )
    daily = sample_bars("1D")
    daily_zones, daily_diagnostics = label_order_blocks(
        daily,
        pd.DataFrame([anchor(daily, 3)]),
        pd.DataFrame(),
        CONFIG,
        pip_size=0.0001,
    )

    assert diagnostics.loc[0, "status"] == "no_opposing_candle"
    assert not bool(diagnostics.loc[0, "candidate_found"])
    assert daily_zones.empty
    assert daily_diagnostics.empty


def test_body_geometry_is_registered_diagnostic_variant() -> None:
    bars = sample_bars()
    zones, _ = label_order_blocks(
        bars,
        pd.DataFrame([anchor(bars, 3)]),
        pd.DataFrame(),
        CONFIG,
        pip_size=0.0001,
        zone_geometry="body_range",
    )

    assert zones.loc[0, "lower_bound"] == pytest.approx(1.09)
    assert zones.loc[0, "upper_bound"] == pytest.approx(1.10)


def test_interval_iou_measures_zone_geometry_overlap() -> None:
    primary = pd.DataFrame(
        [{"event_id": "ob-1", "lower_bound": 0.0, "upper_bound": 10.0}]
    )
    comparison = pd.DataFrame(
        [{"event_id": "ob-1", "lower_bound": 2.0, "upper_bound": 8.0}]
    )

    assert _interval_iou(primary, comparison).iloc[0] == pytest.approx(0.6)
