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
    plateau_tie_break: Literal["rightmost"]
    near_equal_handling: Literal["structural_relationship"]


class VolatilityConfig(StrictModel):
    atr_period: int = Field(ge=2)
    method: Literal["simple_true_range_mean"]


class BreakConfig(StrictModel):
    confirmation: Literal["close"]
    minimum_buffer_atr: float = Field(ge=0)
    displacement_minimum_body_atr: float = Field(gt=0)
    regime_model: Literal["paired_swing_relationships"]
    protected_swing_model: Literal["latest_confirmed_opposing_swing"]
    choch_result_state: Literal["transition"]


class StructureContextConfig(StrictModel):
    daily_role: Literal["regime_only"]
    daily_entry_trigger_enabled: Literal[False]


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
    enabled: Literal[True]
    strategy_admitted: Literal[False]
    status: Literal["phase0_2_failed_geometry_gate"]
    source_timeframes: tuple[Literal["15min", "1H", "4H"], ...]
    anchor_event_types: tuple[Literal["bos", "choch"], ...]
    require_displacement: Literal[True]
    candidate_rule: Literal["last_opposing_non_doji"]
    candidate_lookback_bars: int = Field(ge=1)
    zone_geometry: Literal["full_wick_range"]
    maximum_age_bars: int = Field(ge=1)
    invalidation: Literal["close_beyond_distal_boundary"]
    duplicate_candidate_handling: Literal["first_activation_only"]
    fvg_overlap_required: Literal[False]

    @model_validator(mode="after")
    def validate_order_block_scope(self) -> OrderBlockConfig:
        if self.source_timeframes != ("15min", "1H", "4H"):
            raise ValueError("Order Block source timeframes must be M15, H1, H4")
        if self.anchor_event_types != ("bos", "choch"):
            raise ValueError("Order Block anchors must be BOS and CHoCH")
        return self


class StructureAuditConfig(StrictModel):
    minimum_bar_coverage_ratio: float = Field(gt=0, le=1)
    maximum_ambiguous_swing_fraction: float = Field(ge=0, lt=1)
    minimum_sensitivity_event_agreement: float = Field(gt=0, le=1)
    minimum_events_per_year: int = Field(ge=1)
    minimum_order_block_anchor_coverage: float = Field(gt=0, le=1)
    minimum_order_block_geometry_iou: float = Field(gt=0, le=1)


class StructureConfig(StrictModel):
    swings: SwingConfig
    volatility: VolatilityConfig
    breaks: BreakConfig
    context: StructureContextConfig
    fair_value_gap: FairValueGapConfig
    support_resistance: SupportResistanceConfig
    indicators: IndicatorConfig
    order_block: OrderBlockConfig
    audit: StructureAuditConfig


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


Phase1ModelId = Literal[
    "p0_session_drift",
    "p1_h4_momentum",
    "p2_h4_sr",
    "p3_m15_structure",
    "p4_top_down_structure",
    "p5_top_down_structure_fvg",
]


class Phase1ScopeConfig(StrictModel):
    sessions: tuple[Literal["london", "new_york"], ...]
    construction_year: Literal[2024]
    replication_year: Literal[2025]
    price_only: Literal[True]
    excluded_features: tuple[
        Literal[
            "order_block",
            "h1_support_resistance",
            "fundamental_bias",
            "ema",
            "rsi",
        ],
        ...,
    ]

    @model_validator(mode="after")
    def validate_scope(self) -> Phase1ScopeConfig:
        if self.sessions != ("london", "new_york"):
            raise ValueError("Phase 1 sessions must be London then New York")
        required = {
            "order_block",
            "h1_support_resistance",
            "fundamental_bias",
            "ema",
            "rsi",
        }
        if set(self.excluded_features) != required:
            raise ValueError("Phase 1 exclusions must remain frozen")
        return self


class Phase1OpportunityConfig(StrictModel):
    maximum_trades_per_model_session: Literal[1]
    signal_observation_minutes: int = Field(gt=0)
    require_session_open_m5_bar: Literal[True]


class Phase1BaselineConfig(StrictModel):
    id: Phase1ModelId
    signal: Literal[
        "fitted_fixed_session_direction",
        "latest_completed_h4_close_change",
        "first_causal_h4_zone_breakout_or_rejection",
        "first_m15_bos_or_choch",
        "p3_aligned_with_h1_and_h4_context",
        "p4_with_displacement_and_same_bar_directional_fvg",
    ]


class Phase1SessionDriftConfig(StrictModel):
    fit_period: Literal["construction"]
    fit_separately_by_session: Literal[True]
    candidates: tuple[Literal["long", "short"], ...]
    objective: Literal["mean_primary_net_r"]
    tie_break: Literal["long"]


class Phase1SupportResistanceSignalConfig(StrictModel):
    source_timeframe: Literal["4H"]
    setup_timeframe: Literal["15min"]
    require_zone_active_before_setup_bar: Literal[True]
    maximum_zone_age_h4_bars: int = Field(ge=1)
    breakout_close_buffer_atr: float = Field(ge=0)
    candidate_order: tuple[
        Literal["normalized_distance", "breakout_before_rejection", "zone_id"],
        ...,
    ]


class Phase1StructureSignalConfig(StrictModel):
    setup_timeframe: Literal["15min"]
    event_types: tuple[Literal["bos", "choch"], ...]
    top_down_context_timeframes: tuple[Literal["1H", "4H"], ...]
    daily_role: Literal["report_stratum_only"]
    fvg_same_bar_required: Literal[True]
    fvg_same_direction_required: Literal[True]
    displacement_required_for_fvg_model: Literal[True]


class Phase1RiskConfig(StrictModel):
    stop_atr: float = Field(gt=0)
    target_r: float = Field(gt=0)
    atr_source: Literal["signal_m15_atr"]
    bracket_anchor: Literal["observed_entry_quote_before_slippage"]
    management_cutoff: dict[
        Literal["london", "new_york"],
        Literal["new_york_open", "fx_day_boundary"],
    ]
    force_flat_at_cutoff: Literal[True]
    concurrent_positions_per_model: Literal[1]

    @model_validator(mode="after")
    def validate_cutoffs(self) -> Phase1RiskConfig:
        expected = {
            "london": "new_york_open",
            "new_york": "fx_day_boundary",
        }
        if self.management_cutoff != expected:
            raise ValueError("Phase 1 management cutoffs must remain frozen")
        return self


class Phase1StatisticsConfig(StrictModel):
    comparison_unit: Literal["session_day_opportunity"]
    no_trade_return_r: Literal[0.0]
    bootstrap_unit: Literal["fx_session_date"]
    bootstrap_resamples: int = Field(ge=100)
    confidence_level: float = Field(gt=0, lt=1)
    primary_period: Literal["replication"]
    construction_is_descriptive: Literal[True]


class Phase1AdvancementGateConfig(StrictModel):
    candidates: tuple[
        Literal["p4_top_down_structure", "p5_top_down_structure_fvg"], ...
    ]
    require_zero_causality_failures: Literal[True]
    minimum_trades_per_year: int = Field(ge=1)
    minimum_trades_per_session_replication: int = Field(ge=1)
    minimum_trades_per_direction_replication: int = Field(ge=1)
    require_positive_construction_expectancy: Literal[True]
    require_positive_replication_expectancy: Literal[True]
    require_positive_replication_expectancy_each_session: Literal[True]
    require_positive_replication_expectancy_each_direction: Literal[True]
    require_replication_profit_factor_above_one: Literal[True]
    require_replication_opportunity_mean_ci_above_zero: Literal[True]
    require_positive_stress_replication_expectancy: Literal[True]
    maximum_best_month_share_of_positive_r: float = Field(gt=0, le=1)
    nearest_baseline: dict[
        Literal["p4_top_down_structure", "p5_top_down_structure_fvg"],
        Literal["p3_m15_structure", "p4_top_down_structure"],
    ]
    require_positive_incremental_replication_opportunity_mean: Literal[True]


class Phase1Config(StrictModel):
    phase: Literal["phase1_nested_price_baselines"]
    status: Literal["preregistered"]
    scope: Phase1ScopeConfig
    opportunity: Phase1OpportunityConfig
    baselines: tuple[Phase1BaselineConfig, ...]
    session_drift_fit: Phase1SessionDriftConfig
    support_resistance_signal: Phase1SupportResistanceSignalConfig
    structure_signal: Phase1StructureSignalConfig
    risk: Phase1RiskConfig
    statistics: Phase1StatisticsConfig
    advancement_gate: Phase1AdvancementGateConfig

    @model_validator(mode="after")
    def validate_baseline_ladder(self) -> Phase1Config:
        expected = (
            "p0_session_drift",
            "p1_h4_momentum",
            "p2_h4_sr",
            "p3_m15_structure",
            "p4_top_down_structure",
            "p5_top_down_structure_fvg",
        )
        if tuple(item.id for item in self.baselines) != expected:
            raise ValueError("Phase 1 baseline ladder must remain frozen")
        if self.structure_signal.event_types != ("bos", "choch"):
            raise ValueError("Phase 1 structure events must be BOS then CHoCH")
        return self


class Phase11ParentConfig(StrictModel):
    branch: Literal["phase/01-nested-price-baselines"]
    fingerprint: Literal["daac4b3ee86ac545"]


class Phase11OpportunityConfig(StrictModel):
    maximum_trades_per_model_session: Literal[1]
    setup_signal_window: Literal["full_session"]
    setup_selection: Literal["first_candidate_satisfying_each_model"]
    require_session_open_m5_bar: Literal[True]
    decision_must_be_before_cutoff: Literal[True]
    minimum_minutes_remaining: Literal[0]
    window_end: dict[
        Literal["london", "new_york"],
        Literal["new_york_open", "fx_day_boundary"],
    ]

    @model_validator(mode="after")
    def validate_window_end(self) -> Phase11OpportunityConfig:
        expected = {
            "london": "new_york_open",
            "new_york": "fx_day_boundary",
        }
        if self.window_end != expected:
            raise ValueError("Phase 1.1 session ends must remain frozen")
        return self


class Phase11BaselineConfig(StrictModel):
    id: Phase1ModelId
    signal: Literal[
        "fitted_fixed_session_direction",
        "latest_completed_h4_close_change",
        "first_causal_h4_zone_breakout_or_rejection",
        "first_m15_bos_or_choch",
        "first_m15_structure_aligned_with_h1_and_h4_context",
        "first_aligned_structure_with_displacement_and_directional_fvg",
    ]


class Phase11Config(StrictModel):
    phase: Literal["phase1_1_full_session_setups"]
    status: Literal["preregistered_after_phase1"]
    parent: Phase11ParentConfig
    scope: Phase1ScopeConfig
    opportunity: Phase11OpportunityConfig
    baselines: tuple[Phase11BaselineConfig, ...]
    session_drift_fit: Phase1SessionDriftConfig
    support_resistance_signal: Phase1SupportResistanceSignalConfig
    structure_signal: Phase1StructureSignalConfig
    risk: Phase1RiskConfig
    statistics: Phase1StatisticsConfig
    advancement_gate: Phase1AdvancementGateConfig

    @model_validator(mode="after")
    def validate_revision(self) -> Phase11Config:
        expected = (
            "p0_session_drift",
            "p1_h4_momentum",
            "p2_h4_sr",
            "p3_m15_structure",
            "p4_top_down_structure",
            "p5_top_down_structure_fvg",
        )
        if tuple(item.id for item in self.baselines) != expected:
            raise ValueError("Phase 1.1 baseline ladder must remain frozen")
        return self


Phase12FilterId = Literal[
    "f1_displacement",
    "f2_h1_opposition_veto",
    "f3_h4_opposition_veto",
    "f4_h1_h4_opposition_veto",
    "f5_displacement_h4_veto",
    "f6_displacement_h1_h4_veto",
]
Phase12Rule = Literal[
    "displacement",
    "h1_opposition_veto",
    "h4_opposition_veto",
]


class Phase12ParentConfig(StrictModel):
    branch: Literal["phase/01-1-full-session-setups"]
    fingerprint: Literal["90d1e369b427d3d8"]


class Phase12ScopeConfig(StrictModel):
    baseline_model: Literal["p3_m15_structure"]
    construction_year: Literal[2024]
    replication_year: Literal[2025]
    sessions: tuple[Literal["london", "new_york"], ...]
    excluded_posthoc_filters: tuple[
        Literal["session", "event_type", "local_hour"], ...
    ]
    excluded_features: tuple[
        Literal[
            "order_block",
            "h1_support_resistance",
            "fundamental_bias",
            "ema",
            "rsi",
            "fvg",
        ],
        ...,
    ]


class Phase12CandidateConfig(StrictModel):
    id: Phase12FilterId
    rules: tuple[Phase12Rule, ...]


class Phase12CoverageConfig(StrictModel):
    returns_access_allowed: Literal[False]
    period: Literal["construction"]
    target_trades_per_month_minimum: Literal[20]
    target_trades_per_month_maximum: Literal[25]
    target_trades_per_year_minimum: Literal[240]
    target_trades_per_year_maximum: Literal[300]
    selection: Literal["first_candidate_satisfying_filter_per_session"]
    candidates: tuple[Phase12CandidateConfig, ...]

    @model_validator(mode="after")
    def validate_candidates(self) -> Phase12CoverageConfig:
        expected = {
            "f1_displacement": ("displacement",),
            "f2_h1_opposition_veto": ("h1_opposition_veto",),
            "f3_h4_opposition_veto": ("h4_opposition_veto",),
            "f4_h1_h4_opposition_veto": (
                "h1_opposition_veto",
                "h4_opposition_veto",
            ),
            "f5_displacement_h4_veto": (
                "displacement",
                "h4_opposition_veto",
            ),
            "f6_displacement_h1_h4_veto": (
                "displacement",
                "h1_opposition_veto",
                "h4_opposition_veto",
            ),
        }
        actual = {item.id: item.rules for item in self.candidates}
        if actual != expected:
            raise ValueError("Phase 1.2 light-filter definitions must remain frozen")
        return self


class Phase12DisplacementConfig(StrictModel):
    source_field: Literal["displacement_qualified"]
    required_value: Literal[True]
    frozen_minimum_body_atr: Literal[0.8]


class Phase12VetoConfig(StrictModel):
    timeframe: Literal["1H", "4H"]
    long_rejected_state: Literal["bearish"]
    short_rejected_state: Literal["bullish"]
    allowed_states: tuple[
        Literal["aligned", "transition", "balance", "undetermined"], ...
    ]


class Phase12FilterDefinitionsConfig(StrictModel):
    displacement: Phase12DisplacementConfig
    h1_opposition_veto: Phase12VetoConfig
    h4_opposition_veto: Phase12VetoConfig


class Phase12ConstructionSelectionConfig(StrictModel):
    pnl_access_scope: Literal["construction_eligible_filters_only"]
    baseline_comparison: Literal["p3_m15_structure"]
    require_positive_mean_trade_net_r: Literal[True]
    require_profit_factor_above_one: Literal[True]
    require_mean_opportunity_improvement_over_p3: Literal[True]
    winner_objective: Literal["highest_mean_opportunity_net_r"]
    tie_break_order: tuple[Phase12FilterId, ...]
    maximum_replication_candidates: Literal[1]
    no_qualified_winner_action: Literal["stop_without_replication"]


class Phase12ExecutionConfig(StrictModel):
    inherit_from_phase1_1: Literal[True]
    stop_atr: Literal[1.0]
    target_r: Literal[2.0]
    primary_slippage_pips_per_side: Literal[0.1]
    stress_slippage_pips_per_side: Literal[0.2]
    commission_pips_per_side: Literal[0.35]
    force_flat_at_session_cutoff: Literal[True]


class Phase12ReplicationGateConfig(StrictModel):
    require_frozen_selection_file: Literal[True]
    required_trade_count_minimum: Literal[240]
    required_trade_count_maximum: Literal[300]
    require_positive_mean_trade_net_r: Literal[True]
    require_profit_factor_above_one: Literal[True]
    require_positive_mean_opportunity_net_r: Literal[True]
    require_mean_opportunity_improvement_over_p3: Literal[True]
    require_positive_expectancy_each_session: Literal[True]
    require_positive_expectancy_each_direction: Literal[True]
    require_positive_stress_expectancy: Literal[True]
    require_opportunity_mean_ci_above_zero: Literal[True]
    maximum_best_month_share_of_positive_r: Literal[0.5]


class Phase12Config(StrictModel):
    phase: Literal["phase1_2_light_filter_ablation"]
    status: Literal["preregistered_before_coverage"]
    parent: Phase12ParentConfig
    scope: Phase12ScopeConfig
    coverage_screen: Phase12CoverageConfig
    filter_definitions: Phase12FilterDefinitionsConfig
    construction_selection: Phase12ConstructionSelectionConfig
    execution: Phase12ExecutionConfig
    replication_gate: Phase12ReplicationGateConfig


class Phase12CoverageEligibleConfig(StrictModel):
    id: Literal["f1_displacement", "f4_h1_h4_opposition_veto"]
    trade_count: int = Field(ge=240, le=300)
    mean_trades_per_month: float = Field(ge=20, le=25)


class Phase12CoverageExcludedConfig(StrictModel):
    id: Literal[
        "f2_h1_opposition_veto",
        "f3_h4_opposition_veto",
        "f5_displacement_h4_veto",
        "f6_displacement_h1_h4_veto",
    ]
    trade_count: int = Field(ge=0)
    reason: Literal["above_coverage_maximum", "below_coverage_minimum"]


class Phase12CoverageSelectionConfig(StrictModel):
    phase: Literal["phase1_2_light_filter_ablation"]
    stage: Literal["construction_coverage_only"]
    status: Literal["frozen_before_construction_pnl"]
    coverage_fingerprint: Literal["accd1392cff3c949"]
    parent_fingerprint: Literal["90d1e369b427d3d8"]
    construction_year: Literal[2024]
    target_trade_count: tuple[Literal[240], Literal[300]]
    pnl_inspected: Literal[False]
    eligible_filters: tuple[Phase12CoverageEligibleConfig, ...]
    excluded_filters: tuple[Phase12CoverageExcludedConfig, ...]

    @model_validator(mode="after")
    def validate_frozen_coverage(self) -> Phase12CoverageSelectionConfig:
        eligible = tuple(item.id for item in self.eligible_filters)
        if eligible != ("f1_displacement", "f4_h1_h4_opposition_veto"):
            raise ValueError("Frozen Phase 1.2 coverage selection changed")
        if sum(item.trade_count for item in self.eligible_filters) != 563:
            raise ValueError("Frozen Phase 1.2 coverage counts changed")
        return self


class Phase13ParentConfig(StrictModel):
    branch: Literal["phase/01-1-full-session-setups"]
    fingerprint: Literal["90d1e369b427d3d8"]
    baseline_model: Literal["p3_m15_structure"]


class Phase13ScopeConfig(StrictModel):
    periods: tuple[Literal["construction", "replication"], ...]
    years: tuple[Literal[2024, 2025], ...]
    sessions: tuple[Literal["london", "new_york"], ...]
    signal_selection: Literal["frozen_parent_p3_signals"]
    alter_signals: Literal[False]
    strategy_pnl_selection: Literal[False]


class Phase13PathMeasurementConfig(StrictModel):
    timeframe: Literal["5min"]
    start: Literal["observed_entry_bar"]
    end: Literal["session_cutoff_exclusive"]
    long_entry_quote: Literal["ask_open"]
    long_path_quote: Literal["bid"]
    short_entry_quote: Literal["bid_open"]
    short_path_quote: Literal["ask"]
    anchor: Literal["observed_entry_quote_before_slippage"]
    stop_disabled_during_measurement: Literal[True]
    commission_in_excursion: Literal[False]
    slippage_in_excursion: Literal[False]
    observed_spread_in_excursion: Literal[True]
    same_bar_policy: Literal["ambiguous_stop_first"]
    later_target_requires_later_m5_bar: Literal[True]


class Phase13ThresholdConfig(StrictModel):
    stop_atr_multiples: tuple[
        Literal[1.0, 1.25, 1.5, 2.0], ...
    ]
    fixed_target_atr: Literal[2.0]
    rr_preserving_target_multiple: Literal[2.0]

    @model_validator(mode="after")
    def validate_thresholds(self) -> Phase13ThresholdConfig:
        if self.stop_atr_multiples != (1.0, 1.25, 1.5, 2.0):
            raise ValueError("Phase 1.3 stop thresholds must remain frozen")
        return self


class Phase13ReportingConfig(StrictModel):
    scopes: tuple[Literal["overall", "session", "direction"], ...]
    excursion_quantiles: tuple[Literal[0.25, 0.5, 0.75, 0.9], ...]
    separate_periods: Literal[True]
    report_fixed_target_paths: Literal[True]
    report_rr_preserving_paths: Literal[True]
    winner_selection: Literal["none"]


class Phase13Config(StrictModel):
    phase: Literal["phase1_3_stop_adequacy_audit"]
    status: Literal["preregistered_before_path_audit"]
    parent: Phase13ParentConfig
    scope: Phase13ScopeConfig
    path_measurement: Phase13PathMeasurementConfig
    thresholds: Phase13ThresholdConfig
    reporting: Phase13ReportingConfig

    @model_validator(mode="after")
    def validate_contract(self) -> Phase13Config:
        if self.scope.periods != ("construction", "replication"):
            raise ValueError("Phase 1.3 periods must remain frozen")
        if self.scope.years != (2024, 2025):
            raise ValueError("Phase 1.3 years must remain frozen")
        if self.scope.sessions != ("london", "new_york"):
            raise ValueError("Phase 1.3 sessions must remain frozen")
        if self.reporting.scopes != ("overall", "session", "direction"):
            raise ValueError("Phase 1.3 report scopes must remain frozen")
        return self


class ProjectConfig(StrictModel):
    research: ResearchConfig
    sessions: SessionsConfig
    fundamental: FundamentalConfig
    structure: StructureConfig
    execution: ExecutionConfig
    phase1: Phase1Config
    phase1_1: Phase11Config
    phase1_2: Phase12Config
    phase1_2_coverage_selection: Phase12CoverageSelectionConfig
    phase1_3: Phase13Config


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
        phase1=Phase1Config.model_validate(
            _read_yaml(config_directory / "phase1.yaml")
        ),
        phase1_1=Phase11Config.model_validate(
            _read_yaml(config_directory / "phase1_1.yaml")
        ),
        phase1_2=Phase12Config.model_validate(
            _read_yaml(config_directory / "phase1_2.yaml")
        ),
        phase1_2_coverage_selection=Phase12CoverageSelectionConfig.model_validate(
            _read_yaml(config_directory / "phase1_2_coverage_selection.yaml")
        ),
        phase1_3=Phase13Config.model_validate(
            _read_yaml(config_directory / "phase1_3.yaml")
        ),
    )


def resolve_data_root(project_root: Path, data: DataConfig) -> Path:
    configured = os.environ.get(data.root_environment_variable)
    if configured:
        return Path(configured).expanduser().resolve()
    return (project_root / data.local_fallback).resolve()
