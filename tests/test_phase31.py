from pathlib import Path

import pandas as pd
import pytest

from gbpusd_structure.config import load_project_config
from gbpusd_structure.phase31 import (
    build_execution_mappings,
    setup_membership_hash,
    simulate_signal_bar_trade,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _bar(
    timestamp: str,
    *,
    bid_open: float,
    bid_high: float,
    bid_low: float,
    bid_close: float,
    spread: float = 0.0001,
) -> dict[str, object]:
    at = pd.Timestamp(timestamp)
    return {
        "timestamp": at,
        "available_at": at + pd.Timedelta(5, unit="min"),
        "bar_id": f"5min:{at.isoformat()}",
        "bid_open": bid_open,
        "bid_high": bid_high,
        "bid_low": bid_low,
        "bid_close": bid_close,
        "ask_open": bid_open + spread,
        "ask_high": bid_high + spread,
        "ask_low": bid_low + spread,
        "ask_close": bid_close + spread,
    }


def _setup(direction: str = "long") -> pd.DataFrame:
    signal_at = pd.Timestamp("2024-01-02T08:00:00Z")
    trigger_at = pd.Timestamp("2024-01-02T08:05:00Z")
    return pd.DataFrame(
        [
            {
                "setup_id": "setup:test",
                "opportunity_id": "2024-01-02:london",
                "family": "with_trend_second_entry",
                "session": "london",
                "session_date": "2024-01-02",
                "direction": direction,
                "available_at": trigger_at,
                "cutoff_at": pd.Timestamp("2024-01-02T08:20:00Z"),
                "selected": True,
                "triggered": True,
                "triggered_at": trigger_at + pd.Timedelta(5, unit="min"),
                "trigger_price": 1.2001 if direction == "long" else 1.1999,
                "signal_bar_id": f"5min:{signal_at.isoformat()}",
                "trigger_bar_id": f"5min:{trigger_at.isoformat()}",
            }
        ]
    )


def test_membership_hash_is_order_independent() -> None:
    setups = pd.DataFrame({"setup_id": ["setup:b", "setup:a"]})

    assert setup_membership_hash(setups) == setup_membership_hash(
        setups.iloc[::-1]
    )


def test_long_signal_bar_stop_and_two_r_target() -> None:
    config = load_project_config(PROJECT_ROOT / "config")
    bars = pd.DataFrame(
        [
            _bar(
                "2024-01-02T08:00:00Z",
                bid_open=1.1995,
                bid_high=1.2000,
                bid_low=1.1990,
                bid_close=1.1998,
            ),
            _bar(
                "2024-01-02T08:05:00Z",
                bid_open=1.1999,
                bid_high=1.2025,
                bid_low=1.1995,
                bid_close=1.2020,
            ),
            _bar(
                "2024-01-02T08:10:00Z",
                bid_open=1.2020,
                bid_high=1.2022,
                bid_low=1.2018,
                bid_close=1.2020,
            ),
        ]
    )
    mapping = build_execution_mappings(_setup(), bars, config).iloc[0].to_dict()

    trade = simulate_signal_bar_trade(
        mapping, bars, config, slippage_pips_per_side=0.1
    )

    assert mapping["mapping_status"] == "valid"
    assert mapping["stop_price"] == pytest.approx(1.19899)
    assert mapping["risk_pips"] == pytest.approx(11.1)
    assert mapping["target_price"] == pytest.approx(1.20232)
    assert trade is not None
    assert trade["exit_reason"] == "target_entry_bar"
    assert trade["gross_r"] == pytest.approx(2.0)
    assert trade["net_r"] < 2.0


def test_entry_bar_ambiguity_resolves_stop_first() -> None:
    config = load_project_config(PROJECT_ROOT / "config")
    bars = pd.DataFrame(
        [
            _bar(
                "2024-01-02T08:00:00Z",
                bid_open=1.1995,
                bid_high=1.2000,
                bid_low=1.1990,
                bid_close=1.1998,
            ),
            _bar(
                "2024-01-02T08:05:00Z",
                bid_open=1.1999,
                bid_high=1.2025,
                bid_low=1.1985,
                bid_close=1.2000,
            ),
        ]
    )
    mapping = build_execution_mappings(_setup(), bars, config).iloc[0].to_dict()

    trade = simulate_signal_bar_trade(
        mapping, bars, config, slippage_pips_per_side=0.1
    )

    assert trade is not None
    assert trade["exit_reason"] == "stop_entry_bar_ambiguous"
    assert trade["gross_r"] == pytest.approx(-1.0)
    assert trade["net_r"] < -1.0


def test_stop_entry_gap_uses_worse_executable_open() -> None:
    config = load_project_config(PROJECT_ROOT / "config")
    bars = pd.DataFrame(
        [
            _bar(
                "2024-01-02T08:00:00Z",
                bid_open=1.1995,
                bid_high=1.2000,
                bid_low=1.1990,
                bid_close=1.1998,
            ),
            _bar(
                "2024-01-02T08:05:00Z",
                bid_open=1.2009,
                bid_high=1.2015,
                bid_low=1.2005,
                bid_close=1.2012,
            ),
            _bar(
                "2024-01-02T08:10:00Z",
                bid_open=1.2012,
                bid_high=1.2014,
                bid_low=1.2010,
                bid_close=1.2013,
            ),
        ]
    )

    mapping = build_execution_mappings(_setup(), bars, config).iloc[0]

    assert mapping["entry_gap"]
    assert mapping["entry_reference_price"] == pytest.approx(1.2010)
