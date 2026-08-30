from pathlib import Path

import pandas as pd
import pytest

from gbpusd_structure.config import load_project_config
from gbpusd_structure.phase14 import (
    CANDIDATE_ID,
    DIAGNOSTIC_ID,
    _latest_opposing_swing,
    _simulate_structural_trade,
    attach_structural_stops,
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


def _signal() -> dict[str, object]:
    return {
        "signal_id": "signal:p3:test",
        "source_event_id": "break:test",
        "model_id": "p3_m15_structure",
        "opportunity_id": "2024-01-02:london",
        "session": "london",
        "session_date": "2024-01-02",
        "year": 2024,
        "period": "construction",
        "direction": "long",
        "event_type": "bos",
        "decision_at": pd.Timestamp("2024-01-02T08:00:00Z"),
        "cutoff_at": pd.Timestamp("2024-01-02T08:15:00Z"),
        "atr": 0.001,
    }


def _swing(
    event_id: str,
    event_at: str,
    available_at: str,
    confirmation_index: int,
) -> dict[str, object]:
    return {
        "event_id": event_id,
        "timeframe": "15min",
        "event_type": "swing_low",
        "event_at": pd.Timestamp(event_at),
        "available_at": pd.Timestamp(available_at),
        "ambiguous_equal": False,
        "confirmation_index": confirmation_index,
        "pivot_index": confirmation_index - 2,
        "structural_relationship": "HL",
    }


def test_latest_opposing_swing_excludes_future_confirmation() -> None:
    swings = pd.DataFrame(
        [
            _swing(
                "causal",
                "2024-01-02T07:00:00Z",
                "2024-01-02T07:45:00Z",
                10,
            ),
            _swing(
                "future",
                "2024-01-02T07:30:00Z",
                "2024-01-02T08:15:00Z",
                12,
            ),
        ]
    )

    selected = _latest_opposing_swing(_signal(), swings)

    assert selected is not None
    assert selected["event_id"] == "causal"


def test_long_structural_stop_uses_bid_low_and_signal_atr_buffer() -> None:
    config = load_project_config(PROJECT_ROOT / "config")
    signal = _signal()
    signals = pd.DataFrame([signal])
    swings = pd.DataFrame(
        [
            _swing(
                "causal",
                "2024-01-02T07:00:00Z",
                "2024-01-02T07:45:00Z",
                10,
            )
        ]
    )
    breaks = pd.DataFrame(
        [
            {
                "event_id": "break:test",
                "timeframe": "15min",
                "event_type": "bos",
                "available_at": pd.Timestamp("2024-01-02T08:00:00Z"),
                "direction": "up",
            }
        ]
    )
    m5 = pd.DataFrame(
        [
            _bar(
                "2024-01-02T07:00:00Z",
                bid_open=1.2680,
                bid_high=1.2685,
                bid_low=1.2670,
                bid_close=1.2680,
            ),
            _bar(
                "2024-01-02T07:05:00Z",
                bid_open=1.2680,
                bid_high=1.2684,
                bid_low=1.2668,
                bid_close=1.2675,
            ),
            _bar(
                "2024-01-02T07:10:00Z",
                bid_open=1.2675,
                bid_high=1.2682,
                bid_low=1.2672,
                bid_close=1.2680,
            ),
            _bar(
                "2024-01-02T08:00:00Z",
                bid_open=1.2700,
                bid_high=1.2705,
                bid_low=1.2695,
                bid_close=1.2702,
            ),
            _bar(
                "2024-01-02T08:05:00Z",
                bid_open=1.2702,
                bid_high=1.2710,
                bid_low=1.2700,
                bid_close=1.2708,
            ),
            _bar(
                "2024-01-02T08:10:00Z",
                bid_open=1.2708,
                bid_high=1.2715,
                bid_low=1.2705,
                bid_close=1.2712,
            ),
        ]
    )

    mapping = attach_structural_stops(signals, swings, breaks, m5, config).iloc[0]

    assert mapping["mapping_status"] == "valid"
    assert mapping["entry_reference_price"] == pytest.approx(1.2701)
    assert mapping["structural_unbuffered_level"] == pytest.approx(1.2668)
    assert mapping["structural_stop_price"] == pytest.approx(1.2667)
    assert mapping["structural_stop_atr"] == pytest.approx(3.4)


def test_candidate_target_is_two_times_structural_risk() -> None:
    config = load_project_config(PROJECT_ROOT / "config")
    setup = {
        **_signal(),
        "mapping_status": "valid",
        "structural_stop_price": 1.2691,
    }
    m5 = pd.DataFrame(
        [
            _bar(
                "2024-01-02T08:00:00Z",
                bid_open=1.2700,
                bid_high=1.2722,
                bid_low=1.2695,
                bid_close=1.2720,
            ),
            _bar(
                "2024-01-02T08:05:00Z",
                bid_open=1.2720,
                bid_high=1.2723,
                bid_low=1.2715,
                bid_close=1.2721,
            ),
            _bar(
                "2024-01-02T08:10:00Z",
                bid_open=1.2721,
                bid_high=1.2722,
                bid_low=1.2718,
                bid_close=1.2720,
            ),
        ]
    )

    trade = _simulate_structural_trade(
        setup,
        m5,
        config,
        variant_id=CANDIDATE_ID,
        slippage_pips_per_side=0.1,
    )

    assert trade is not None
    assert trade["risk_pips"] == pytest.approx(10.0)
    assert trade["target_price"] == pytest.approx(1.2721)
    assert trade["target_r_before_costs"] == pytest.approx(2.0)
    assert trade["exit_reason"] == "target"
    assert trade["net_r"] == pytest.approx(1.91)
    assert trade["theoretical_lots"] == pytest.approx(0.3)


def test_diagnostic_target_stays_two_signal_atr() -> None:
    config = load_project_config(PROJECT_ROOT / "config")
    setup = {
        **_signal(),
        "mapping_status": "valid",
        "structural_stop_price": 1.2681,
    }
    m5 = pd.DataFrame(
        [
            _bar(
                "2024-01-02T08:00:00Z",
                bid_open=1.2700,
                bid_high=1.2722,
                bid_low=1.2695,
                bid_close=1.2720,
            ),
            _bar(
                "2024-01-02T08:05:00Z",
                bid_open=1.2720,
                bid_high=1.2723,
                bid_low=1.2715,
                bid_close=1.2721,
            ),
            _bar(
                "2024-01-02T08:10:00Z",
                bid_open=1.2721,
                bid_high=1.2722,
                bid_low=1.2718,
                bid_close=1.2720,
            ),
        ]
    )

    trade = _simulate_structural_trade(
        setup,
        m5,
        config,
        variant_id=DIAGNOSTIC_ID,
        slippage_pips_per_side=0.1,
    )

    assert trade is not None
    assert trade["risk_pips"] == pytest.approx(20.0)
    assert trade["target_price"] == pytest.approx(1.2721)
    assert trade["target_r_before_costs"] == pytest.approx(1.0)
