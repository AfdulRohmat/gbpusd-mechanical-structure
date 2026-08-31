import pandas as pd

from gbpusd_structure.phase12 import (
    FORBIDDEN_COVERAGE_COLUMN_PARTS,
    _construction_metrics,
    filter_candidate_mask,
    select_first_filter_candidates,
)


def _candidates() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "opportunity_id": "one",
                "decision_at": pd.Timestamp("2024-01-02T08:15:00Z"),
                "source_event_id": "early",
                "direction": "long",
                "displacement_qualified": False,
                "h1_context": "bearish",
                "h4_context": "transition",
            },
            {
                "opportunity_id": "one",
                "decision_at": pd.Timestamp("2024-01-02T09:00:00Z"),
                "source_event_id": "later",
                "direction": "long",
                "displacement_qualified": True,
                "h1_context": "transition",
                "h4_context": "bullish",
            },
            {
                "opportunity_id": "two",
                "decision_at": pd.Timestamp("2024-01-02T13:15:00Z"),
                "source_event_id": "short_opposed",
                "direction": "short",
                "displacement_qualified": True,
                "h1_context": "transition",
                "h4_context": "bullish",
            },
        ]
    )


def test_opposition_veto_rejects_only_explicit_opposite_state() -> None:
    frame = _candidates()

    mask = filter_candidate_mask(frame, ("h4_opposition_veto",))

    assert mask.tolist() == [True, True, False]


def test_filter_selects_later_candidate_that_satisfies_complete_rule() -> None:
    selected = select_first_filter_candidates(
        _candidates(),
        "f6_displacement_h1_h4_veto",
        ("displacement", "h1_opposition_veto", "h4_opposition_veto"),
    )

    assert selected["source_event_id"].tolist() == ["later"]


def test_coverage_forbidden_names_include_execution_outcomes() -> None:
    assert "net_r" in FORBIDDEN_COVERAGE_COLUMN_PARTS
    assert "exit" in FORBIDDEN_COVERAGE_COLUMN_PARTS


def test_construction_metrics_use_common_opportunity_denominator() -> None:
    opportunities = pd.DataFrame({"opportunity_id": ["one", "two"]})
    trades = pd.DataFrame(
        {
            "model_id": ["f1_displacement"],
            "net_r": [1.0],
            "win": [True],
        }
    )

    metrics = _construction_metrics(
        opportunities,
        trades,
        ("f1_displacement",),
    ).iloc[0]

    assert metrics["mean_trade_net_r"] == 1.0
    assert metrics["mean_opportunity_net_r"] == 0.5
