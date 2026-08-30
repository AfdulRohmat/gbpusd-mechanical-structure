from pathlib import Path

import pandas as pd
import pytest

from gbpusd_structure.config import load_project_config
from gbpusd_structure.phase15 import E1, _simulate_delayed_trade

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
    return {
        "timestamp": pd.Timestamp(timestamp),
        "bid_open": bid_open,
        "bid_high": bid_high,
        "bid_low": bid_low,
        "bid_close": bid_close,
        "ask_open": bid_open + spread,
        "ask_high": bid_high + spread,
        "ask_low": bid_low + spread,
        "ask_close": bid_close + spread,
    }


def test_pullback_entry_keeps_absolute_target_and_improves_target_r() -> None:
    config = load_project_config(PROJECT_ROOT / "config")
    mapping = {
        "signal_id": "signal:test",
        "opportunity_id": "2024-01-02:london",
        "model_id": "p3_m15_structure",
        "session": "london",
        "session_date": "2024-01-02",
        "year": 2024,
        "period": "construction",
        "direction": "long",
        "event_type": "bos",
        "decision_at": pd.Timestamp("2024-01-02T08:00:00Z"),
        "cutoff_at": pd.Timestamp("2024-01-02T08:15:00Z"),
        "atr": 0.001,
        "structural_stop_price": 1.2681,
        "entry_reference_price": 1.2701,
    }
    coverage = {
        "model_id": E1,
        "entry_at": pd.Timestamp("2024-01-02T08:00:00Z"),
        "entry_decision_at": pd.Timestamp("2024-01-02T08:00:00Z"),
        "m5_fvg_id": "fvg:test",
        "m5_fvg_available_at": pd.Timestamp("2024-01-02T07:50:00Z"),
        "m5_mitigation_bar_at": pd.Timestamp("2024-01-02T07:55:00Z"),
        "m1_fvg_id": None,
        "m1_fvg_available_at": None,
    }
    bars = pd.DataFrame(
        [
            _bar(
                "2024-01-02T08:00:00Z",
                bid_open=1.2690,
                bid_high=1.2722,
                bid_low=1.2688,
                bid_close=1.2720,
            ),
            _bar(
                "2024-01-02T08:05:00Z",
                bid_open=1.2720,
                bid_high=1.2723,
                bid_low=1.2718,
                bid_close=1.2721,
            ),
            _bar(
                "2024-01-02T08:10:00Z",
                bid_open=1.2721,
                bid_high=1.2722,
                bid_low=1.2719,
                bid_close=1.2720,
            ),
        ]
    )

    trade = _simulate_delayed_trade(
        coverage,
        mapping,
        bars,
        config,
        slippage_pips_per_side=0.1,
    )

    assert trade is not None
    assert trade["target_price"] == pytest.approx(1.2721)
    assert trade["risk_pips"] == pytest.approx(10.0)
    assert trade["target_r_before_costs"] == pytest.approx(3.0)
    assert trade["exit_reason"] == "target"
    assert trade["net_r"] == pytest.approx(2.91)
