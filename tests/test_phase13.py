from pathlib import Path

import pandas as pd
import pytest

from gbpusd_structure.config import load_project_config
from gbpusd_structure.phase13 import (
    _sequence_label,
    build_excursion_audit,
    summarize_threshold_paths,
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


def _signal(direction: str = "long") -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "signal_id": "signal:p3:test",
                "opportunity_id": "2024-01-02:london",
                "session": "london",
                "session_date": "2024-01-02",
                "year": 2024,
                "period": "construction",
                "direction": direction,
                "event_type": "bos",
                "decision_at": pd.Timestamp("2024-01-02T08:00:00Z"),
                "cutoff_at": pd.Timestamp("2024-01-02T08:15:00Z"),
                "atr": 0.001,
            }
        ]
    )


def test_sequence_requires_target_in_strictly_later_bar() -> None:
    label, stop_position, target_position = _sequence_label(
        adverse_path_atr=pd.Series([1.1, 1.2, 1.2]).to_numpy(),
        favorable_path_atr=pd.Series([0.2, 1.0, 2.1]).to_numpy(),
        stop_atr=1.0,
        target_atr=2.0,
    )

    assert label == "stop_then_target_later"
    assert stop_position == 0
    assert target_position == 2


def test_same_bar_touch_remains_ambiguous_stop_first() -> None:
    label, _, _ = _sequence_label(
        adverse_path_atr=pd.Series([0.2, 1.1]).to_numpy(),
        favorable_path_atr=pd.Series([0.1, 2.1]).to_numpy(),
        stop_atr=1.0,
        target_atr=2.0,
    )

    assert label == "same_bar_ambiguous_stop_first"


def test_long_audit_uses_ask_entry_and_bid_path() -> None:
    config = load_project_config(PROJECT_ROOT / "config")
    m5 = pd.DataFrame(
        [
            _bar(
                "2024-01-02T08:00:00Z",
                bid_open=1.2700,
                bid_high=1.2702,
                bid_low=1.2690,
                bid_close=1.2695,
            ),
            _bar(
                "2024-01-02T08:05:00Z",
                bid_open=1.2695,
                bid_high=1.2710,
                bid_low=1.2692,
                bid_close=1.2708,
            ),
            _bar(
                "2024-01-02T08:10:00Z",
                bid_open=1.2708,
                bid_high=1.2722,
                bid_low=1.2705,
                bid_close=1.2720,
            ),
        ]
    )

    excursions, paths = build_excursion_audit(_signal(), m5, config)

    assert excursions.iloc[0]["entry_reference_price"] == pytest.approx(1.2701)
    assert excursions.iloc[0]["max_adverse_excursion_atr"] == pytest.approx(1.1)
    assert excursions.iloc[0]["max_favorable_excursion_atr"] == pytest.approx(2.1)
    original = paths[
        paths["stop_atr"].eq(1.0) & paths["target_mode"].eq("fixed_2atr")
    ].iloc[0]
    assert original["sequence"] == "stop_then_target_later"


def test_wider_stop_can_save_original_premature_path() -> None:
    config = load_project_config(PROJECT_ROOT / "config")
    m5 = pd.DataFrame(
        [
            _bar(
                "2024-01-02T08:00:00Z",
                bid_open=1.2700,
                bid_high=1.2702,
                bid_low=1.2690,
                bid_close=1.2695,
            ),
            _bar(
                "2024-01-02T08:05:00Z",
                bid_open=1.2695,
                bid_high=1.2710,
                bid_low=1.2692,
                bid_close=1.2708,
            ),
            _bar(
                "2024-01-02T08:10:00Z",
                bid_open=1.2708,
                bid_high=1.2722,
                bid_low=1.2705,
                bid_close=1.2720,
            ),
        ]
    )

    _, paths = build_excursion_audit(_signal(), m5, config)
    wider = paths[
        paths["stop_atr"].eq(1.25) & paths["target_mode"].eq("fixed_2atr")
    ].iloc[0]

    assert wider["sequence"] == "target_before_stop"
    assert bool(wider["saved_original_premature"])

    summary = summarize_threshold_paths(paths, config)
    row = summary[
        summary["scope"].eq("overall")
        & summary["stop_atr"].eq(1.0)
        & summary["target_mode"].eq("fixed_2atr")
    ].iloc[0]
    assert row["strict_premature_stop_rate"] == pytest.approx(1.0)
