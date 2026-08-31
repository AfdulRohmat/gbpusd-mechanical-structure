from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from gbpusd_structure.config import (
    ResearchConfig,
    load_project_config,
    resolve_data_root,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_checked_in_configuration_is_valid() -> None:
    config = load_project_config(PROJECT_ROOT / "config")

    assert config.research.instrument.symbol == "GBPUSD"
    assert config.research.instrument.account_type == "Raw Spread"
    assert config.research.data.price_source == "histdata_bid_ask"
    assert config.research.timeframes.context == ("1D", "4H", "1H")
    assert config.sessions.sessions["london"].timezone == "Europe/London"
    assert config.fundamental.usage.role == "context_filter"
    assert config.structure.swings.right_bars == 2
    assert config.structure.swings.near_equal_handling == "structural_relationship"
    assert config.structure.breaks.choch_result_state == "transition"
    assert config.structure.context.daily_entry_trigger_enabled is False
    assert config.structure.order_block.enabled is True
    assert config.structure.order_block.strategy_admitted is False
    assert config.structure.order_block.candidate_lookback_bars == 6
    assert config.structure.order_block.maximum_age_bars == 50
    assert config.phase1.scope.price_only is True
    assert "order_block" in config.phase1.scope.excluded_features
    assert config.phase1.advancement_gate.candidates == (
        "p4_top_down_structure",
        "p5_top_down_structure_fvg",
    )
    assert config.phase1.risk.stop_atr == pytest.approx(1.0)
    assert config.phase1.risk.target_r == pytest.approx(2.0)
    assert config.phase1_1.opportunity.setup_signal_window == "full_session"
    assert (
        config.phase1_1.opportunity.setup_selection
        == "first_candidate_satisfying_each_model"
    )
    assert config.phase1_1.opportunity.minimum_minutes_remaining == 0
    assert config.phase1_1.parent.fingerprint == "daac4b3ee86ac545"
    assert config.phase1_2.parent.fingerprint == "90d1e369b427d3d8"
    assert config.phase1_2.coverage_screen.returns_access_allowed is False
    assert config.phase1_2.coverage_screen.target_trades_per_year_minimum == 240
    assert config.phase1_2.coverage_screen.target_trades_per_year_maximum == 300
    assert config.phase1_2_coverage_selection.pnl_inspected is False
    assert tuple(
        item.id for item in config.phase1_2_coverage_selection.eligible_filters
    ) == ("f1_displacement", "f4_h1_h4_opposition_veto")
    assert config.phase1_3.parent.fingerprint == "90d1e369b427d3d8"
    assert config.phase1_3.parent.baseline_model == "p3_m15_structure"
    assert config.phase1_3.thresholds.stop_atr_multiples == (
        1.0,
        1.25,
        1.5,
        2.0,
    )
    assert config.phase1_3.path_measurement.stop_disabled_during_measurement
    assert config.phase1_4.parent.fingerprint == "90d1e369b427d3d8"
    assert config.phase1_4.invalidation.buffer_signal_atr == pytest.approx(0.1)
    assert config.phase1_4.invalidation.distance_filter == "none"
    assert tuple(item.id for item in config.phase1_4.variants) == (
        "p3_atr_1_target_2atr",
        "p3_structure_target_2atr",
        "p3_structure_target_2r",
    )
    assert config.phase1_4.risk.fixed_risk_usd == pytest.approx(30.0)
    assert config.phase1_5.parent.structural_construction_fingerprint == (
        "41fe02f5ef90868b"
    )
    assert config.phase1_5.fvg.minimum_size_atr == pytest.approx(0.1)
    assert config.phase1_5.coverage_stage.minimum_evaluable_trades_per_year == 120
    assert config.phase1_5.coverage_stage.desired_trades_per_year == (240, 300)
    assert tuple(item.id for item in config.phase1_5.variants) == (
        "e0_immediate_structure_2atr",
        "e1_m5_fvg_mitigation",
        "e2_m5_fvg_m1_refinement",
    )
    assert config.phase1_5_coverage_selection.returns_inspected is False
    assert tuple(
        (item.id, item.entry_count)
        for item in config.phase1_5_coverage_selection.eligible_candidates
    ) == (
        ("e1_m5_fvg_mitigation", 250),
        ("e2_m5_fvg_m1_refinement", 170),
    )
    assert config.phase2.scope.construction_year == 2024
    assert config.phase2.scope.historical_replication_access_allowed is False
    assert config.phase2.events.primitives == (
        "bos",
        "choch",
        "liquidity_sweep",
        "displacement",
    )
    assert config.phase2.outcomes.forward_horizons_minutes == (
        15,
        30,
        60,
        120,
        240,
    )
    assert config.phase2.outcomes.primary_horizon_minutes == 60
    assert config.phase2.baselines.recent_breakout_lookback_m15_bars == 4
    assert config.phase2.decision_gate.minimum_primary_events == 120
    assert config.phase4.parent.expected_signal_count == 383
    assert config.phase4.scope.evaluation_year == 2025
    assert config.phase4.scope.construction_candidate_returns_access_allowed is False
    assert tuple(item.id for item in config.phase4.variants) == (
        "structure_stop_target_2atr_baseline",
        "structure_stop_target_2atr_be_after_1atr",
    )
    assert config.phase4.protection.favorable_trigger_signal_atr == pytest.approx(1.0)
    assert config.phase4.bracket.target_signal_atr == pytest.approx(2.0)
    assert (
        config.phase4.historical_gate.require_positive_paired_improvement_over_baseline
    )
    assert config.execution.pricing.broker_specific_spread_claim is False
    assert config.execution.costs.commission_pips_per_side == pytest.approx(0.35)


def test_local_data_root_is_default(monkeypatch: pytest.MonkeyPatch) -> None:
    config = load_project_config(PROJECT_ROOT / "config")
    monkeypatch.delenv("GBPUSD_SHARED_DATA_ROOT", raising=False)

    assert resolve_data_root(PROJECT_ROOT, config.research.data) == (
        PROJECT_ROOT / "data"
    ).resolve()


def test_environment_data_root_overrides_local(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config = load_project_config(PROJECT_ROOT / "config")
    monkeypatch.setenv("GBPUSD_SHARED_DATA_ROOT", str(tmp_path))

    assert resolve_data_root(PROJECT_ROOT, config.research.data) == tmp_path.resolve()


def test_research_config_rejects_unknown_key() -> None:
    raw = yaml.safe_load(
        (PROJECT_ROOT / "config/research.yaml").read_text(encoding="utf-8")
    )
    raw["instrument"]["unregistered"] = True

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ResearchConfig.model_validate(raw)
