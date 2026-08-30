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
