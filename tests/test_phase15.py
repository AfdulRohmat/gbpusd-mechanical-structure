import pandas as pd

from gbpusd_structure.phase15 import (
    E1,
    _coverage_invariant_failures,
    label_lower_timeframe_fvgs,
)


def _bars() -> pd.DataFrame:
    rows = []
    timestamp = pd.Timestamp("2024-01-02T08:00:00Z")
    for index in range(16):
        base = 1.2700 + index * 0.0001
        rows.append(
            {
                "timestamp": timestamp + pd.Timedelta(index * 5, unit="min"),
                "mid_open": base,
                "mid_high": base + 0.0001,
                "mid_low": base - 0.0001,
                "mid_close": base + 0.00005,
            }
        )
    rows[-3].update(mid_high=1.2710, mid_low=1.2708)
    rows[-2].update(mid_high=1.2715, mid_low=1.2711)
    rows[-1].update(mid_high=1.2720, mid_low=1.2713)
    return pd.DataFrame(rows)


def test_lower_timeframe_fvg_is_available_only_after_third_close() -> None:
    fvgs = label_lower_timeframe_fvgs(
        _bars(),
        timeframe="5min",
        minutes=5,
        atr_period=14,
        minimum_size_atr=0.1,
    )

    bullish = fvgs[fvgs["direction"].eq("long")].iloc[-1]
    assert bullish["third_bar_at"] == pd.Timestamp("2024-01-02T09:15:00Z")
    assert bullish["available_at"] == pd.Timestamp("2024-01-02T09:20:00Z")
    assert bullish["lower_bound"] == 1.2710
    assert bullish["upper_bound"] == 1.2713


def test_non_contiguous_bars_cannot_form_fvg() -> None:
    bars = _bars().drop(index=14).reset_index(drop=True)
    fvgs = label_lower_timeframe_fvgs(
        bars,
        timeframe="5min",
        minutes=5,
        atr_period=14,
        minimum_size_atr=0.1,
    )

    assert not fvgs["third_bar_at"].eq(pd.Timestamp("2024-01-02T09:15:00Z")).any()


def test_coverage_artifact_rejects_return_column() -> None:
    coverage = pd.DataFrame(
        [
            {
                "model_id": E1,
                "opportunity_id": "2024-01-02:london",
                "coverage_status": "entry",
                "entry_at": pd.Timestamp("2024-01-02T08:10:00Z"),
                "entry_decision_at": pd.Timestamp("2024-01-02T08:10:00Z"),
                "cutoff_at": pd.Timestamp("2024-01-02T13:00:00Z"),
                "period": "construction",
                "m5_mitigation_bar_at": pd.Timestamp("2024-01-02T08:05:00Z"),
                "m5_fvg_available_at": pd.Timestamp("2024-01-02T08:00:00Z"),
                "m1_fvg_available_at": pd.NaT,
                "net_r": 1.0,
            }
        ]
    )

    failures = _coverage_invariant_failures(coverage)

    assert any(
        item["invariant"] == "coverage_return_columns_forbidden"
        for item in failures
    )
