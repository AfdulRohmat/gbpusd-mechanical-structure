from pathlib import Path

import pandas as pd
import pytest

from gbpusd_structure.config import load_project_config
from gbpusd_structure.phase1 import (
    _invariant_failures,
    _select_first_structure_signal,
    _simulate_trade,
    build_full_session_opportunities,
    build_session_opportunities,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _m5_bar(
    timestamp: str,
    *,
    bid_open: float,
    bid_high: float,
    bid_low: float,
    bid_close: float,
    spread: float = 0.00008,
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


def _signal(direction: str = "long") -> dict[str, object]:
    return {
        "model_id": "p3_m15_structure",
        "opportunity_id": "2024-01-02:london",
        "decision_at": pd.Timestamp("2024-01-02T08:00:00Z"),
        "cutoff_at": pd.Timestamp("2024-01-02T08:15:00Z"),
        "direction": direction,
        "atr": 0.001,
    }


def test_long_target_uses_ask_entry_bid_exit_and_full_costs() -> None:
    config = load_project_config(PROJECT_ROOT / "config")
    m5 = pd.DataFrame(
        [
            _m5_bar(
                "2024-01-02T08:00:00Z",
                bid_open=1.27000,
                bid_high=1.27220,
                bid_low=1.26990,
                bid_close=1.27200,
            )
        ]
    )

    trade = _simulate_trade(
        _signal(),
        m5,
        config,
        slippage_pips_per_side=0.10,
    )

    assert trade is not None
    assert trade["exit_reason"] == "target"
    assert trade["entry_reference_price"] == pytest.approx(1.27008)
    assert trade["net_r"] == pytest.approx(1.91)


def test_stop_wins_when_stop_and_target_touch_same_bar() -> None:
    config = load_project_config(PROJECT_ROOT / "config")
    m5 = pd.DataFrame(
        [
            _m5_bar(
                "2024-01-02T08:00:00Z",
                bid_open=1.27000,
                bid_high=1.27250,
                bid_low=1.26850,
                bid_close=1.27000,
            )
        ]
    )

    trade = _simulate_trade(
        _signal(),
        m5,
        config,
        slippage_pips_per_side=0.10,
    )

    assert trade is not None
    assert trade["exit_reason"] == "stop"
    assert trade["net_r"] == pytest.approx(-1.09)


def test_session_calendar_resolves_london_dst() -> None:
    config = load_project_config(PROJECT_ROOT / "config")
    m5 = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [
                    "2024-01-02T08:00:00Z",
                    "2024-01-02T13:00:00Z",
                    "2024-07-02T07:00:00Z",
                    "2024-07-02T12:00:00Z",
                ]
            )
        }
    )

    opportunities = build_session_opportunities(m5, config)

    london = opportunities[opportunities["session"].eq("london")]
    assert set(london["session_open_at"].dt.hour) == {7, 8}


def test_full_session_observation_ends_at_management_cutoff() -> None:
    config = load_project_config(PROJECT_ROOT / "config")
    m5 = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [
                    "2024-01-02T08:00:00Z",
                    "2024-01-02T13:00:00Z",
                ]
            )
        }
    )

    opportunities = build_full_session_opportunities(m5, config)

    assert opportunities["observation_end_at"].equals(opportunities["cutoff_at"])


def test_each_model_can_select_its_own_later_valid_candidate() -> None:
    candidates = pd.DataFrame(
        [
            {
                "opportunity_id": "2024-01-02:london",
                "decision_at": pd.Timestamp("2024-01-02T08:15:00Z"),
                "source_event_id": "first_unaligned",
                "model_id": "p3_m15_structure",
                "signal_type": "candidate",
                "signal_id": "candidate:first",
            },
            {
                "opportunity_id": "2024-01-02:london",
                "decision_at": pd.Timestamp("2024-01-02T10:00:00Z"),
                "source_event_id": "later_aligned",
                "model_id": "p3_m15_structure",
                "signal_type": "candidate",
                "signal_id": "candidate:later",
            },
        ]
    )

    p3 = _select_first_structure_signal(
        candidates,
        model_id="p3_m15_structure",
        signal_type="first_structure",
    )
    p4 = _select_first_structure_signal(
        candidates[candidates["source_event_id"].eq("later_aligned")],
        model_id="p4_top_down_structure",
        signal_type="first_aligned_structure",
    )

    assert p3.iloc[0]["source_event_id"] == "first_unaligned"
    assert p4.iloc[0]["source_event_id"] == "later_aligned"


def test_invariants_reject_child_without_parent() -> None:
    signals = pd.DataFrame(
        [
            {
                "model_id": "p4_top_down_structure",
                "opportunity_id": "2024-01-02:london",
                "direction": "long",
                "feature_available_at": pd.Timestamp("2024-01-02T08:00:00Z"),
                "decision_at": pd.Timestamp("2024-01-02T08:00:00Z"),
                "session_open_at": pd.Timestamp("2024-01-02T08:00:00Z"),
                "observation_end_at": pd.Timestamp("2024-01-02T09:30:00Z"),
            }
        ]
    )
    trades = pd.DataFrame(
        columns=[
            "entry_at",
            "decision_at",
            "cutoff_at",
            "exit_at",
            "model_id",
            "opportunity_id",
        ]
    )

    failures = _invariant_failures(signals, trades)

    assert any(
        item["invariant"]
        == "p4_top_down_structure_subset_of_p3_m15_structure"
        for item in failures
    )
