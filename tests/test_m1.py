import zipfile
from pathlib import Path

import pandas as pd

from gbpusd_structure.m1 import (
    iter_histdata_ticks,
    reconcile_m1_to_m5,
    resample_ticks_m1,
)


def test_histdata_m1_uses_fixed_est_and_preserves_bid_ask(tmp_path: Path) -> None:
    path = tmp_path / "ticks.zip"
    rows = "\n".join(
        (
            "20240102 030000000,1.27000,1.27020,0",
            "20240102 030059999,1.27010,1.27030,0",
            "20240102 030100000,1.27020,1.27040,0",
        )
    )
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("DAT_ASCII_GBPUSD_T_202401.csv", rows)

    ticks = pd.concat(
        list(iter_histdata_ticks(path, pip_size=0.0001, chunksize=2)),
        ignore_index=True,
    )
    bars = resample_ticks_m1(ticks)

    assert ticks.iloc[0]["timestamp"] == pd.Timestamp("2024-01-02T08:00:00Z")
    assert len(bars) == 2
    assert bars.iloc[0]["bid_open"] == 1.27000
    assert bars.iloc[0]["bid_close"] == 1.27010
    assert bars.iloc[0]["ask_high"] == 1.27030
    assert bars.iloc[0]["tick_count"] == 2


def test_m1_reconciles_exactly_to_m5() -> None:
    timestamps = pd.date_range("2024-01-02T08:00:00Z", periods=5, freq="1min")
    m1 = pd.DataFrame(
        {
            "timestamp": timestamps,
            "bid_open": [1.0, 1.1, 1.2, 1.3, 1.4],
            "bid_high": [1.1, 1.2, 1.3, 1.4, 1.5],
            "bid_low": [0.9, 1.0, 1.1, 1.2, 1.3],
            "bid_close": [1.05, 1.15, 1.25, 1.35, 1.45],
            "ask_open": [1.01, 1.11, 1.21, 1.31, 1.41],
            "ask_high": [1.11, 1.21, 1.31, 1.41, 1.51],
            "ask_low": [0.91, 1.01, 1.11, 1.21, 1.31],
            "ask_close": [1.06, 1.16, 1.26, 1.36, 1.46],
            "mid_open": [1.005, 1.105, 1.205, 1.305, 1.405],
            "mid_high": [1.105, 1.205, 1.305, 1.405, 1.505],
            "mid_low": [0.905, 1.005, 1.105, 1.205, 1.305],
            "mid_close": [1.055, 1.155, 1.255, 1.355, 1.455],
            "tick_count": [2, 3, 4, 5, 6],
        }
    )
    m5 = pd.DataFrame(
        {
            "timestamp": [timestamps[0]],
            "bid_open": [1.0],
            "bid_high": [1.5],
            "bid_low": [0.9],
            "bid_close": [1.45],
            "ask_open": [1.01],
            "ask_high": [1.51],
            "ask_low": [0.91],
            "ask_close": [1.46],
            "mid_open": [1.005],
            "mid_high": [1.505],
            "mid_low": [0.905],
            "mid_close": [1.455],
            "tick_count": [20],
        }
    )

    result = reconcile_m1_to_m5(m1, m5)

    assert result["valid"] is True
    assert sum(result["column_mismatch_count"].values()) == 0
