from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest

from gbpusd_structure.timeframes import (
    aggregate_m5,
    fx_anchored_boundaries,
    fx_trading_week_mask,
)


def sample_m5(start: datetime, count: int) -> pd.DataFrame:
    timestamp = pd.to_datetime(
        [start + timedelta(minutes=5 * index) for index in range(count)], utc=True
    )
    base = pd.Series([1.2700 + index * 0.0001 for index in range(count)])
    frame = pd.DataFrame({"timestamp": timestamp})
    for side, offset in (("bid", 0.0), ("ask", 0.0001), ("mid", 0.00005)):
        frame[f"{side}_open"] = base + offset
        frame[f"{side}_high"] = base + offset + 0.00005
        frame[f"{side}_low"] = base + offset - 0.00005
        frame[f"{side}_close"] = base + offset + 0.00002
    frame["tick_count"] = 10
    frame["activity_count"] = 10
    frame["spread_open_pips"] = 1.0
    frame["spread_median_pips"] = 1.0
    frame["spread_p95_pips"] = 1.2
    frame["spread_max_pips"] = 1.5
    return frame


def test_m15_aggregation_and_availability() -> None:
    source = sample_m5(datetime(2024, 1, 2, 8, tzinfo=UTC), 3)
    bars = aggregate_m5(source, "15min")

    assert len(bars) == 1
    assert bars.loc[0, "timestamp"] == pd.Timestamp("2024-01-02 08:00", tz="UTC")
    assert bars.loc[0, "available_at"] == pd.Timestamp(
        "2024-01-02 08:15", tz="UTC"
    )
    assert bars.loc[0, "source_m5_count"] == 3
    assert bars.loc[0, "coverage_ratio"] == 1
    assert bars.loc[0, "mid_open"] == pytest.approx(1.27005)
    assert bars.loc[0, "mid_close"] == pytest.approx(1.27027)


def test_h4_is_anchored_to_17_new_york_across_dst() -> None:
    timestamps = pd.Series(
        pd.to_datetime(
            ["2024-01-02 22:00:00+00:00", "2024-07-02 21:00:00+00:00"],
            utc=True,
        )
    )
    starts, ends = fx_anchored_boundaries(timestamps, "4H")

    assert starts.tolist() == timestamps.tolist()
    assert (ends - starts).dt.total_seconds().tolist() == [14_400, 14_400]


def test_partial_bar_preserves_coverage_failure() -> None:
    source = sample_m5(datetime(2024, 1, 2, 8, tzinfo=UTC), 2)
    bars = aggregate_m5(source, "15min")

    assert bars.loc[0, "source_m5_count"] == 2
    assert bars.loc[0, "expected_m5_count"] == 3
    assert bars.loc[0, "coverage_ratio"] == pytest.approx(2 / 3)


def test_fx_week_excludes_friday_after_close_but_keeps_sunday_open() -> None:
    timestamps = pd.Series(
        pd.to_datetime(
            [
                "2024-07-05 20:55:00+00:00",
                "2024-07-05 21:00:00+00:00",
                "2024-07-07 20:55:00+00:00",
                "2024-07-07 21:00:00+00:00",
            ],
            utc=True,
        )
    )

    assert fx_trading_week_mask(timestamps).tolist() == [True, False, False, True]
