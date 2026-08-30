"""Strict configuration contracts for mechanical-structure research."""

from __future__ import annotations

import os
import re
from datetime import date, time
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def _validate_timezone(value: str) -> str:
    try:
        ZoneInfo(value)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"Unknown IANA timezone: {value}") from exc
    return value


class InstrumentConfig(StrictModel):
    symbol: Literal["GBPUSD"]
    broker: Literal["Exness"]
    account_type: Literal["Raw Spread"]
    platform: Literal["MT5"]
    pip_size: float = Field(gt=0)
    price_decimals: int = Field(ge=1, le=10)


class DataConfig(StrictModel):
    root_environment_variable: str
    local_fallback: Path
    price_source: Literal["histdata_bid_ask", "exness_mt5_bid_ask"]
    source_role: Literal["temporary_development_proxy", "broker_execution_feed"]
    canonical_m5_glob: str
    fundamental_directory: Path
    timezone: Literal["UTC"]

    @model_validator(mode="after")
    def validate_root_environment_variable(self) -> DataConfig:
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", self.root_environment_variable):
            raise ValueError("data root environment variable must be uppercase")
        if Path(self.canonical_m5_glob).is_absolute():
            raise ValueError("canonical_m5_glob must be relative to the data root")
        return self


class EvidencePeriodsConfig(StrictModel):
    research_start: date
    research_end: date
    construction_end: date
    replication_end: date
    future_lockbox_start: date

    @model_validator(mode="after")
    def validate_periods(self) -> EvidencePeriodsConfig:
        if not (
            self.research_start
            < self.construction_end
            < self.replication_end
            == self.research_end
            < self.future_lockbox_start
        ):
            raise ValueError("research and lockbox boundaries must be increasing")
        return self


class TimeframesConfig(StrictModel):
    context: tuple[Literal["1D", "4H", "1H"], ...]
    setup: Literal["15min"]
    execution: Literal["5min"]
    fx_day_boundary_timezone: str
    fx_day_boundary: time

    @model_validator(mode="after")
    def validate_timeframes(self) -> TimeframesConfig:
        if self.context != ("1D", "4H", "1H"):
            raise ValueError("context timeframes must be ordered 1D, 4H, 1H")
        _validate_timezone(self.fx_day_boundary_timezone)
        return self


class QualityConfig(StrictModel):
    reject_crossed_quotes: bool
    minimum_m5_coverage_ratio: float = Field(gt=0, le=1)
    exclude_weekends: bool
    maximum_spread_pips_warning: float = Field(gt=0)


class StudyConfig(StrictModel):
    random_seed: int = Field(ge=0)
    bootstrap_resamples: int = Field(ge=100)
    confidence_level: float = Field(gt=0, lt=1)


class ResearchConfig(StrictModel):
    instrument: InstrumentConfig
    data: DataConfig
    periods: EvidencePeriodsConfig
    timeframes: TimeframesConfig
    quality: QualityConfig
    study: StudyConfig


class SessionWindowConfig(StrictModel):
    timezone: str
    open: time
    observation_minutes: int = Field(gt=0)
    management_cutoff: Literal["new_york_open", "fx_day_boundary"]

    @model_validator(mode="after")
    def validate_window(self) -> SessionWindowConfig:
        _validate_timezone(self.timezone)
        if self.observation_minutes % 5:
            raise ValueError("session observation window must be M5-aligned")
        return self


Weekday = Literal["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]


class SessionsConfig(StrictModel):
    sessions: dict[Literal["london", "new_york"], SessionWindowConfig]
    entry_days: tuple[Weekday, ...]

    @model_validator(mode="after")
    def validate_sessions(self) -> SessionsConfig:
        if set(self.sessions) != {"london", "new_york"}:
            raise ValueError("sessions must contain london and new_york")
        required_days = {"Monday", "Tuesday", "Wednesday", "Thursday", "Friday"}
        if set(self.entry_days) != required_days or len(self.entry_days) != 5:
            raise ValueError("entry_days must contain each weekday exactly once")
        return self


class FundamentalWeightsConfig(StrictModel):
    policy: int = Field(ge=1)
    inflation: int = Field(ge=1)
    labor: int = Field(ge=1)
    yield_expectation: int = Field(ge=1)


class FundamentalScoringConfig(StrictModel):
    components: tuple[
        Literal["policy", "inflation", "labor", "yield_expectation"], ...
    ]
    primary_weights: FundamentalWeightsConfig
    primary_bias_threshold: int = Field(ge=1)
    impact_weighted_sensitivity: FundamentalWeightsConfig
    impact_weighted_bias_threshold: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_components(self) -> FundamentalScoringConfig:
        required = {"policy", "inflation", "labor", "yield_expectation"}
        if set(self.components) != required or len(self.components) != len(required):
            raise ValueError("fundamental components must match the frozen set")
        if set(self.primary_weights.model_dump().values()) != {1}:
            raise ValueError("primary fundamental weights must remain equal to one")
        return self


class FundamentalAvailabilityConfig(StrictModel):
    require_point_in_time_release_timestamp: Literal[True]
    release_lag_minutes: int = Field(ge=0)
    yield_observation_lag_days: int = Field(ge=1)


class FundamentalUsageConfig(StrictModel):
    role: Literal["context_filter"]
    allow_standalone_entry: Literal[False]
    missing_bias_action: Literal["neutral"]


class FundamentalConfig(StrictModel):
    scoring: FundamentalScoringConfig
    availability: FundamentalAvailabilityConfig
    usage: FundamentalUsageConfig


class SwingConfig(StrictModel):
    left_bars: int = Field(ge=1)
    right_bars: int = Field(ge=1)
    equal_price_tolerance_pips: float = Field(ge=0)


class BreakConfig(StrictModel):
    confirmation: Literal["close"]
    minimum_buffer_atr: float = Field(ge=0)
    displacement_minimum_body_atr: float = Field(gt=0)


class FairValueGapConfig(StrictModel):
    geometry: Literal["three_candle_wick_gap"]
    minimum_size_atr: float = Field(ge=0)
    maximum_age_bars: int = Field(ge=1)
    invalidation: Literal["full_fill"]


class SupportResistanceConfig(StrictModel):
    source_timeframes: tuple[Literal["4H", "1H"], ...]
    cluster_tolerance_atr: float = Field(gt=0)
    minimum_confirmed_touches: int = Field(ge=2)
    maximum_age_bars: int = Field(ge=1)


class IndicatorConfig(StrictModel):
    ema_periods: tuple[int, ...]
    rsi_period: int = Field(ge=2)
    primary_signal_enabled: Literal[False]

    @model_validator(mode="after")
    def validate_ema_periods(self) -> IndicatorConfig:
        unique_periods = tuple(sorted(set(self.ema_periods)))
        if not self.ema_periods or unique_periods != self.ema_periods:
            raise ValueError("EMA periods must be sorted and unique")
        return self


class OrderBlockConfig(StrictModel):
    enabled: Literal[False]
    status: Literal["deferred_pending_operational_definition"]


class StructureConfig(StrictModel):
    swings: SwingConfig
    breaks: BreakConfig
    fair_value_gap: FairValueGapConfig
    support_resistance: SupportResistanceConfig
    indicators: IndicatorConfig
    order_block: OrderBlockConfig


class ExecutionPricingConfig(StrictModel):
    mode: Literal["observed_bid_ask"]
    source: Literal["histdata", "exness_mt5"]
    broker_specific_spread_claim: Literal[False]
    replacement_feed: Literal["exness_mt5_raw_spread"]


class ExecutionCostsConfig(StrictModel):
    commission_usd_per_lot_per_side: float = Field(ge=0)
    usd_per_pip_per_standard_lot: float = Field(gt=0)
    slippage_pips_per_side: float = Field(ge=0)
    stress_slippage_pips_per_side: float = Field(ge=0)
    swap_enabled: Literal[False]

    @model_validator(mode="after")
    def validate_costs(self) -> ExecutionCostsConfig:
        if self.stress_slippage_pips_per_side < self.slippage_pips_per_side:
            raise ValueError("stress slippage must not be below primary slippage")
        return self

    @property
    def commission_pips_per_side(self) -> float:
        return (
            self.commission_usd_per_lot_per_side
            / self.usd_per_pip_per_standard_lot
        )


class ExecutionSimulationConfig(StrictModel):
    intrabar_priority: Literal["stop_first"]
    long_entry_quote: Literal["ask"]
    long_exit_quote: Literal["bid"]
    short_entry_quote: Literal["bid"]
    short_exit_quote: Literal["ask"]


class ExecutionConfig(StrictModel):
    pricing: ExecutionPricingConfig
    costs: ExecutionCostsConfig
    simulation: ExecutionSimulationConfig


class ProjectConfig(StrictModel):
    research: ResearchConfig
    sessions: SessionsConfig
    fundamental: FundamentalConfig
    structure: StructureConfig
    execution: ExecutionConfig


def _read_yaml(path: Path) -> object:
    try:
        with path.open(encoding="utf-8") as stream:
            content = yaml.safe_load(stream)
    except FileNotFoundError as exc:
        raise ValueError(f"Configuration file not found: {path}") from exc
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid YAML in {path}: {exc}") from exc
    if not isinstance(content, dict):
        raise ValueError(f"Configuration root must be a mapping: {path}")
    return content


def load_project_config(config_directory: Path) -> ProjectConfig:
    return ProjectConfig(
        research=ResearchConfig.model_validate(
            _read_yaml(config_directory / "research.yaml")
        ),
        sessions=SessionsConfig.model_validate(
            _read_yaml(config_directory / "sessions.yaml")
        ),
        fundamental=FundamentalConfig.model_validate(
            _read_yaml(config_directory / "fundamental.yaml")
        ),
        structure=StructureConfig.model_validate(
            _read_yaml(config_directory / "structure.yaml")
        ),
        execution=ExecutionConfig.model_validate(
            _read_yaml(config_directory / "execution.yaml")
        ),
    )


def resolve_data_root(project_root: Path, data: DataConfig) -> Path:
    configured = os.environ.get(data.root_environment_variable)
    if configured:
        return Path(configured).expanduser().resolve()
    return (project_root / data.local_fallback).resolve()
