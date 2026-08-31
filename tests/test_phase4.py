from pathlib import Path

import pandas as pd
import pytest

from gbpusd_structure.config import load_project_config
from gbpusd_structure.phase4 import (
    BASELINE_ID,
    CANDIDATE_ID,
    _trade_path,
    signal_membership_sha256,
    simulate_management_variants,
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


def _setup() -> dict[str, object]:
    return {
        "signal_id": "signal:p3:test",
        "source_event_id": "break:test",
        "model_id": "p3_m15_structure",
        "opportunity_id": "2025-01-02:london",
        "session": "london",
        "session_date": "2025-01-02",
        "year": 2025,
        "period": "replication",
        "direction": "long",
        "event_type": "bos",
        "decision_at": pd.Timestamp("2025-01-02T08:00:00Z"),
        "cutoff_at": pd.Timestamp("2025-01-02T08:15:00Z"),
        "atr": 0.001,
        "mapping_status": "valid",
        "structural_stop_price": 1.2681,
    }


def test_membership_hash_is_sorted_and_uses_trailing_newline() -> None:
    first = signal_membership_sha256(pd.Series(["signal:b", "signal:a"]))
    second = signal_membership_sha256(pd.Series(["signal:a", "signal:b"]))

    assert first == second
    assert first == "e7655a16fe713da399a1e9759ebe13e5ff2f1e981e8faff946dbece5f625dbf4"


def test_baseline_keeps_structure_stop_and_fixed_two_atr_target() -> None:
    config = load_project_config(PROJECT_ROOT / "config")
    bars = pd.DataFrame(
        [
            _bar(
                "2025-01-02T08:00:00Z",
                bid_open=1.2700,
                bid_high=1.2722,
                bid_low=1.2695,
                bid_close=1.2720,
            ),
            _bar(
                "2025-01-02T08:05:00Z",
                bid_open=1.2720,
                bid_high=1.2723,
                bid_low=1.2715,
                bid_close=1.2721,
            ),
            _bar(
                "2025-01-02T08:10:00Z",
                bid_open=1.2721,
                bid_high=1.2722,
                bid_low=1.2718,
                bid_close=1.2720,
            ),
        ]
    )

    trade = _trade_path(_setup(), bars, config, variant_id=BASELINE_ID)

    assert trade is not None
    assert trade["hard_stop_price"] == pytest.approx(1.2681)
    assert trade["target_price"] == pytest.approx(1.2721)
    assert trade["target_r_before_costs"] == pytest.approx(1.0)
    assert trade["exit_reason"] == "target"
    assert trade["protection_triggered"] is False


def test_protection_activates_only_on_bar_after_completed_trigger_bar() -> None:
    config = load_project_config(PROJECT_ROOT / "config")
    bars = pd.DataFrame(
        [
            _bar(
                "2025-01-02T08:00:00Z",
                bid_open=1.2700,
                bid_high=1.2712,
                bid_low=1.2695,
                bid_close=1.2705,
            ),
            _bar(
                "2025-01-02T08:05:00Z",
                bid_open=1.2704,
                bid_high=1.2706,
                bid_low=1.2699,
                bid_close=1.2700,
            ),
            _bar(
                "2025-01-02T08:10:00Z",
                bid_open=1.2700,
                bid_high=1.2702,
                bid_low=1.2698,
                bid_close=1.2700,
            ),
        ]
    )

    trade = _trade_path(_setup(), bars, config, variant_id=CANDIDATE_ID)

    assert trade is not None
    assert trade["trigger_observed_at"] == pd.Timestamp("2025-01-02T08:05:00Z")
    assert trade["protection_active_from"] == pd.Timestamp(
        "2025-01-02T08:05:00Z"
    )
    assert trade["exit_at"] == pd.Timestamp("2025-01-02T08:10:00Z")
    assert trade["exit_reason"] == "protected_stop"
    assert trade["raw_exit_price"] == pytest.approx(1.2701)


def test_hard_stop_wins_inside_trigger_bar() -> None:
    config = load_project_config(PROJECT_ROOT / "config")
    bars = pd.DataFrame(
        [
            _bar(
                "2025-01-02T08:00:00Z",
                bid_open=1.2700,
                bid_high=1.2712,
                bid_low=1.2680,
                bid_close=1.2705,
            ),
            _bar(
                "2025-01-02T08:05:00Z",
                bid_open=1.2705,
                bid_high=1.2707,
                bid_low=1.2700,
                bid_close=1.2704,
            ),
            _bar(
                "2025-01-02T08:10:00Z",
                bid_open=1.2704,
                bid_high=1.2706,
                bid_low=1.2701,
                bid_close=1.2703,
            ),
        ]
    )

    trade = _trade_path(_setup(), bars, config, variant_id=CANDIDATE_ID)

    assert trade is not None
    assert trade["exit_reason"] == "hard_stop"
    assert trade["raw_exit_price"] == pytest.approx(1.2681)
    assert trade["protection_triggered"] is False


def test_protected_stop_gap_uses_worse_executable_open() -> None:
    config = load_project_config(PROJECT_ROOT / "config")
    bars = pd.DataFrame(
        [
            _bar(
                "2025-01-02T08:00:00Z",
                bid_open=1.2700,
                bid_high=1.2712,
                bid_low=1.2695,
                bid_close=1.2708,
            ),
            _bar(
                "2025-01-02T08:05:00Z",
                bid_open=1.2697,
                bid_high=1.2700,
                bid_low=1.2695,
                bid_close=1.2698,
            ),
            _bar(
                "2025-01-02T08:10:00Z",
                bid_open=1.2698,
                bid_high=1.2700,
                bid_low=1.2696,
                bid_close=1.2699,
            ),
        ]
    )

    trade = _trade_path(_setup(), bars, config, variant_id=CANDIDATE_ID)

    assert trade is not None
    assert trade["exit_reason"] == "protected_stop_gap"
    assert trade["raw_exit_price"] == pytest.approx(1.2697)


def test_variants_are_identical_when_trigger_is_never_reached() -> None:
    config = load_project_config(PROJECT_ROOT / "config")
    bars = pd.DataFrame(
        [
            _bar(
                "2025-01-02T08:00:00Z",
                bid_open=1.2700,
                bid_high=1.2708,
                bid_low=1.2695,
                bid_close=1.2704,
            ),
            _bar(
                "2025-01-02T08:05:00Z",
                bid_open=1.2704,
                bid_high=1.2707,
                bid_low=1.2698,
                bid_close=1.2703,
            ),
            _bar(
                "2025-01-02T08:10:00Z",
                bid_open=1.2703,
                bid_high=1.2706,
                bid_low=1.2699,
                bid_close=1.2702,
            ),
        ]
    )
    mappings = pd.DataFrame([_setup()])

    trades = simulate_management_variants(
        mappings,
        bars,
        config,
        slippage_pips_per_side=0.1,
    ).set_index("model_id")

    baseline = trades.loc[BASELINE_ID]
    candidate = trades.loc[CANDIDATE_ID]
    assert candidate["raw_exit_price"] == pytest.approx(baseline["raw_exit_price"])
    assert candidate["exit_at"] == baseline["exit_at"]
    assert candidate["exit_reason"] == baseline["exit_reason"]
    assert candidate["net_r"] == pytest.approx(baseline["net_r"])
