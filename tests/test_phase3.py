from pathlib import Path

import pandas as pd

from gbpusd_structure.config import load_project_config
from gbpusd_structure.phase3 import select_session_setups

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_session_selection_is_chronological_and_respects_caps() -> None:
    config = load_project_config(PROJECT_ROOT / "config")
    candidates = pd.DataFrame(
        [
            {
                "setup_id": f"setup-{index}",
                "family": "with_trend_second_entry",
                "opportunity_id": "2024-01-02:new_york",
                "session": "new_york",
                "available_at": pd.Timestamp(f"2024-01-02 13:{minute:02d}:00+00:00"),
                "eligible_signal": eligible,
            }
            for index, (minute, eligible) in enumerate(
                [(5, True), (10, False), (15, True), (20, True)]
            )
        ]
    )

    selected = select_session_setups(candidates, config)

    assert selected["selected"].sum() == 2
    assert set(selected[selected["selected"]]["setup_id"]) == {
        "setup-0",
        "setup-2",
    }
