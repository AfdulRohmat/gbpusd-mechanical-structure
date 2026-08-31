"""Phase-4 structural-stop and fixed-2-ATR trade-management evaluation."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from gbpusd_structure.config import ProjectConfig, load_project_config
from gbpusd_structure.data import canonical_m5_paths, load_canonical_m5
from gbpusd_structure.phase0 import _fingerprint, _prepare_bars, _primary_labels
from gbpusd_structure.phase14 import attach_structural_stops

BASELINE_ID = "structure_stop_target_2atr_baseline"
CANDIDATE_ID = "structure_stop_target_2atr_be_after_1atr"
VARIANT_IDS = (BASELINE_ID, CANDIDATE_ID)


@dataclass(frozen=True)
class Phase4Result:
    artifact_directory: Path
    summary: dict[str, Any]


def signal_membership_sha256(signal_ids: pd.Series) -> str:
    """Hash sorted signal IDs using the preregistered trailing-newline format."""

    payload = "".join(f"{value}\n" for value in sorted(signal_ids.astype(str)))
    return hashlib.sha256(payload.encode()).hexdigest()


def _trade_path(
    setup: dict[str, Any],
    m5: pd.DataFrame,
    config: ProjectConfig,
    *,
    variant_id: str,
) -> dict[str, Any] | None:
    if variant_id not in VARIANT_IDS:
        raise ValueError(f"Unknown Phase 4 variant: {variant_id}")
    if setup["mapping_status"] != "valid":
        return None

    timestamps = pd.to_datetime(m5["timestamp"], utc=True)
    timestamp_values = timestamps.astype("int64").to_numpy()
    decision_at = pd.Timestamp(setup["decision_at"])
    cutoff_at = pd.Timestamp(setup["cutoff_at"])
    entry_position = int(
        np.searchsorted(timestamp_values, decision_at.value, side="left")
    )
    cutoff_position = int(
        np.searchsorted(timestamp_values, cutoff_at.value, side="left")
    )
    if entry_position >= len(m5) or entry_position >= cutoff_position:
        return None

    entry_bar = m5.iloc[entry_position]
    entry_at = pd.Timestamp(entry_bar["timestamp"])
    direction = str(setup["direction"])
    hard_stop = float(setup["structural_stop_price"])
    signal_atr = float(setup["atr"])
    if direction == "long":
        reference_entry = float(entry_bar["ask_open"])
        structural_distance = reference_entry - hard_stop
        target = reference_entry + config.phase4.bracket.target_signal_atr * signal_atr
        trigger = (
            reference_entry
            + config.phase4.protection.favorable_trigger_signal_atr * signal_atr
        )
    else:
        reference_entry = float(entry_bar["bid_open"])
        structural_distance = hard_stop - reference_entry
        target = reference_entry - config.phase4.bracket.target_signal_atr * signal_atr
        trigger = (
            reference_entry
            - config.phase4.protection.favorable_trigger_signal_atr * signal_atr
        )
    if not np.isfinite(structural_distance) or structural_distance <= 0:
        return None

    protection_active = False
    trigger_observed_at = pd.NaT
    protection_active_from = pd.NaT
    raw_exit: float | None = None
    exit_at = pd.NaT
    exit_reason: str | None = None

    for position in range(entry_position, cutoff_position):
        bar = m5.iloc[position]
        bar_at = pd.Timestamp(bar["timestamp"])
        active_stop = reference_entry if protection_active else hard_stop
        if direction == "long":
            quote_open = float(bar["bid_open"])
            stop_touch = float(bar["bid_low"]) <= active_stop
            target_touch = float(bar["bid_high"]) >= target
            if quote_open <= active_stop:
                raw_exit = quote_open
                exit_reason = (
                    "protected_stop_gap" if protection_active else "hard_stop_gap"
                )
            elif quote_open >= target:
                raw_exit = target
                exit_reason = "target_gap"
            elif stop_touch:
                raw_exit = active_stop
                exit_reason = (
                    "protected_stop" if protection_active else "hard_stop"
                )
            elif target_touch:
                raw_exit = target
                exit_reason = "target"
            favorable_trigger = float(bar["bid_high"]) >= trigger
        else:
            quote_open = float(bar["ask_open"])
            stop_touch = float(bar["ask_high"]) >= active_stop
            target_touch = float(bar["ask_low"]) <= target
            if quote_open >= active_stop:
                raw_exit = quote_open
                exit_reason = (
                    "protected_stop_gap" if protection_active else "hard_stop_gap"
                )
            elif quote_open <= target:
                raw_exit = target
                exit_reason = "target_gap"
            elif stop_touch:
                raw_exit = active_stop
                exit_reason = (
                    "protected_stop" if protection_active else "hard_stop"
                )
            elif target_touch:
                raw_exit = target
                exit_reason = "target"
            favorable_trigger = float(bar["ask_low"]) <= trigger

        if raw_exit is not None:
            bar_close_at = bar_at + timedelta(minutes=5)
            exit_at = cutoff_at if bar_close_at > cutoff_at else bar_close_at
            break

        if (
            variant_id == CANDIDATE_ID
            and not protection_active
            and favorable_trigger
        ):
            bar_close_at = bar_at + timedelta(minutes=5)
            trigger_observed_at = (
                cutoff_at if bar_close_at > cutoff_at else bar_close_at
            )
            next_position = position + 1
            if next_position < cutoff_position:
                protection_active = True
                protection_active_from = pd.Timestamp(
                    m5.iloc[next_position]["timestamp"]
                )

    if raw_exit is None:
        final_bar = m5.iloc[cutoff_position - 1]
        raw_exit = float(
            final_bar["bid_close"]
            if direction == "long"
            else final_bar["ask_close"]
        )
        final_bar_close_at = pd.Timestamp(final_bar["timestamp"]) + timedelta(
            minutes=5
        )
        exit_at = (
            cutoff_at if final_bar_close_at > cutoff_at else final_bar_close_at
        )
        exit_reason = "time"

    return {
        **setup,
        "parent_model_id": setup["model_id"],
        "model_id": variant_id,
        "trade_id": f"trade:{variant_id}:{setup['signal_id']}",
        "entry_at": entry_at,
        "exit_at": exit_at,
        "entry_reference_price": reference_entry,
        "raw_exit_price": raw_exit,
        "hard_stop_price": hard_stop,
        "active_protected_stop_price": (
            reference_entry if variant_id == CANDIDATE_ID else None
        ),
        "target_price": target,
        "trigger_price": trigger if variant_id == CANDIDATE_ID else None,
        "trigger_observed_at": trigger_observed_at,
        "protection_active_from": protection_active_from,
        "protection_triggered": bool(pd.notna(trigger_observed_at)),
        "protection_activated": bool(pd.notna(protection_active_from)),
        "exit_reason": exit_reason,
        "structural_risk_price": structural_distance,
        "target_signal_atr": config.phase4.bracket.target_signal_atr,
        "target_r_before_costs": (
            config.phase4.bracket.target_signal_atr
            * signal_atr
            / structural_distance
        ),
    }


def _apply_costs(
    raw_trades: pd.DataFrame,
    config: ProjectConfig,
    *,
    slippage_pips_per_side: float,
) -> pd.DataFrame:
    output = raw_trades.copy()
    pip_size = config.research.instrument.pip_size
    slip = slippage_pips_per_side * pip_size
    is_long = output["direction"].eq("long")
    output["entry_fill_price"] = np.where(
        is_long,
        output["entry_reference_price"] + slip,
        output["entry_reference_price"] - slip,
    )
    output["exit_fill_price"] = np.where(
        is_long,
        output["raw_exit_price"] - slip,
        output["raw_exit_price"] + slip,
    )
    output["pnl_pips_before_commission"] = np.where(
        is_long,
        (output["exit_fill_price"] - output["entry_fill_price"]) / pip_size,
        (output["entry_fill_price"] - output["exit_fill_price"]) / pip_size,
    )
    commission = 2 * config.phase4.execution.commission_pips_per_side
    output["commission_pips_round_trip"] = commission
    output["slippage_pips_per_side"] = slippage_pips_per_side
    output["net_pips"] = output["pnl_pips_before_commission"] - commission
    output["risk_pips"] = output["structural_risk_price"] / pip_size
    output["net_r"] = output["net_pips"] / output["risk_pips"]
    fixed_risk = config.phase4.risk.fixed_geometric_risk_usd
    pip_value = config.phase4.risk.usd_per_pip_per_standard_lot
    output["fixed_risk_usd"] = fixed_risk
    output["theoretical_lots"] = fixed_risk / (output["risk_pips"] * pip_value)
    output["net_usd_at_fixed_risk"] = output["net_r"] * fixed_risk
    output["win"] = output["net_pips"].gt(0)
    return output


def simulate_management_variants(
    mappings: pd.DataFrame,
    m5: pd.DataFrame,
    config: ProjectConfig,
    *,
    slippage_pips_per_side: float,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for setup in mappings.to_dict("records"):
        for variant_id in VARIANT_IDS:
            trade = _trade_path(setup, m5, config, variant_id=variant_id)
            if trade is not None:
                rows.append(trade)
    raw = pd.DataFrame.from_records(rows)
    if raw.empty:
        return raw
    return _apply_costs(
        raw,
        config,
        slippage_pips_per_side=slippage_pips_per_side,
    )


def _profit_factor(values: pd.Series) -> float | None:
    positive = float(values[values.gt(0)].sum())
    negative = abs(float(values[values.lt(0)].sum()))
    return positive / negative if negative else None


def _maximum_drawdown(frame: pd.DataFrame) -> float | None:
    if frame.empty:
        return None
    ordered = frame.sort_values(["exit_at", "trade_id"], kind="stable")
    equity = ordered["net_r"].cumsum().to_numpy()
    equity_with_origin = np.concatenate(([0.0], equity))
    peaks = np.maximum.accumulate(equity_with_origin)
    return float((peaks - equity_with_origin).max())


def build_metrics(trades: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for model_id in VARIANT_IDS:
        model = trades[trades["model_id"].eq(model_id)]
        scopes = [("overall", "all", model)]
        scopes.extend(
            ("session", value, model[model["session"].eq(value)])
            for value in ("london", "new_york")
        )
        scopes.extend(
            ("direction", value, model[model["direction"].eq(value)])
            for value in ("long", "short")
        )
        for scope, value, frame in scopes:
            net = frame["net_r"]
            rows.append(
                {
                    "model_id": model_id,
                    "year": int(frame["year"].iloc[0]) if len(frame) else None,
                    "scope": scope,
                    "value": value,
                    "trade_count": len(frame),
                    "win_count": int(frame["win"].sum()),
                    "win_rate": float(frame["win"].mean()) if len(frame) else None,
                    "total_net_r": float(net.sum()),
                    "mean_trade_net_r": float(net.mean()) if len(net) else None,
                    "median_trade_net_r": float(net.median()) if len(net) else None,
                    "profit_factor": _profit_factor(net),
                    "maximum_drawdown_r": _maximum_drawdown(frame),
                }
            )
    return pd.DataFrame.from_records(rows)


def _paired_differences(trades: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "signal_id",
        "session_date",
        "session",
        "direction",
        "net_r",
    ]
    baseline = trades[trades["model_id"].eq(BASELINE_ID)][columns]
    candidate = trades[trades["model_id"].eq(CANDIDATE_ID)][columns]
    paired = baseline.merge(
        candidate,
        on=["signal_id", "session_date", "session", "direction"],
        how="outer",
        suffixes=("_baseline", "_candidate"),
        indicator=True,
        validate="one_to_one",
    )
    paired["net_r_difference"] = (
        paired["net_r_candidate"] - paired["net_r_baseline"]
    )
    return paired


def _paired_cluster_bootstrap(
    paired: pd.DataFrame,
    config: ProjectConfig,
) -> dict[str, Any]:
    complete = paired[paired["_merge"].eq("both")]
    daily = complete.groupby("session_date", sort=True)["net_r_difference"].agg(
        ["sum", "count"]
    )
    if daily.empty:
        return {
            "cluster_count": 0,
            "estimate": None,
            "ci_lower": None,
            "ci_upper": None,
        }
    rng = np.random.default_rng(config.phase4.statistics.random_seed)
    resamples = config.phase4.statistics.bootstrap_resamples
    positions = rng.integers(0, len(daily), size=(resamples, len(daily)))
    estimates = (
        daily["sum"].to_numpy()[positions].sum(axis=1)
        / daily["count"].to_numpy()[positions].sum(axis=1)
    )
    alpha = 1 - config.phase4.statistics.confidence_level
    return {
        "cluster_count": len(daily),
        "resamples": resamples,
        "estimate": float(complete["net_r_difference"].mean()),
        "ci_lower": float(np.quantile(estimates, alpha / 2)),
        "ci_upper": float(np.quantile(estimates, 1 - alpha / 2)),
    }


def _monthly_summary(trades: pd.DataFrame) -> pd.DataFrame:
    scoped = trades.copy()
    scoped["month"] = (
        pd.to_datetime(scoped["session_date"]).dt.to_period("M").astype(str)
    )
    return (
        scoped.groupby(["model_id", "month"], sort=True)
        .agg(
            trade_count=("trade_id", "size"),
            win_rate=("win", "mean"),
            total_net_r=("net_r", "sum"),
            mean_trade_net_r=("net_r", "mean"),
        )
        .reset_index()
    )


def _best_month_share(monthly: pd.DataFrame) -> float | None:
    candidate = monthly[monthly["model_id"].eq(CANDIDATE_ID)]["total_net_r"]
    positive = candidate[candidate.gt(0)]
    return float(positive.max() / positive.sum()) if len(positive) else None


def _exit_summary(trades: pd.DataFrame) -> pd.DataFrame:
    return (
        trades.groupby(["model_id", "exit_reason"], sort=True)
        .agg(
            trade_count=("trade_id", "size"),
            total_net_r=("net_r", "sum"),
            mean_trade_net_r=("net_r", "mean"),
        )
        .reset_index()
    )


def _invariant_failures(
    signals: pd.DataFrame,
    mappings: pd.DataFrame,
    primary: pd.DataFrame,
    stress: pd.DataFrame,
    config: ProjectConfig,
) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []

    def add(name: str, count: int) -> None:
        if count:
            failures.append({"invariant": name, "failure_count": int(count)})

    expected_count = config.phase4.parent.expected_signal_count
    add("parent_signal_count", abs(len(signals) - expected_count))
    actual_hash = signal_membership_sha256(signals["signal_id"])
    add(
        "parent_signal_membership_hash",
        int(actual_hash != config.phase4.parent.signal_membership_sha256),
    )
    add("duplicate_parent_signal", int(signals["signal_id"].duplicated().sum()))
    add("mapping_count_matches_parent", abs(len(mappings) - len(signals)))
    add("duplicate_mapping_signal", int(mappings["signal_id"].duplicated().sum()))
    add("source_event_reproduced", int((~mappings["source_event_match"]).sum()))
    add(
        "valid_structural_mapping",
        int(mappings["mapping_status"].ne("valid").sum()),
    )
    add(
        "swing_available_by_decision",
        int(
            mappings["structural_swing_available_at"]
            .gt(mappings["decision_at"])
            .sum()
        ),
    )
    add(
        "swing_pivot_before_decision",
        int(
            mappings["structural_swing_event_at"]
            .ge(mappings["decision_at"])
            .sum()
        ),
    )
    add(
        "evaluation_year_only_mappings",
        int(mappings["year"].ne(config.phase4.scope.evaluation_year).sum()),
    )

    valid_count = int(mappings["mapping_status"].eq("valid").sum())
    for label, trades in (("primary", primary), ("stress", stress)):
        add(
            f"{label}_evaluation_year_only",
            int(trades["year"].ne(config.phase4.scope.evaluation_year).sum()),
        )
        add(
            f"{label}_exit_by_cutoff",
            int(trades["exit_at"].gt(trades["cutoff_at"]).sum()),
        )
        for variant_id in VARIANT_IDS:
            variant = trades[trades["model_id"].eq(variant_id)]
            add(
                f"{label}_{variant_id}_trade_count",
                abs(len(variant) - valid_count),
            )
            add(
                f"{label}_{variant_id}_duplicate_signal",
                int(variant["signal_id"].duplicated().sum()),
            )

    comparison_columns = [
        "signal_id",
        "entry_at",
        "entry_reference_price",
        "hard_stop_price",
        "target_price",
    ]
    baseline = primary[primary["model_id"].eq(BASELINE_ID)][comparison_columns]
    candidate = primary[primary["model_id"].eq(CANDIDATE_ID)][comparison_columns]
    pair = baseline.merge(
        candidate,
        on="signal_id",
        how="outer",
        suffixes=("_baseline", "_candidate"),
        indicator=True,
        validate="one_to_one",
    )
    add("variant_membership_identical", int(pair["_merge"].ne("both").sum()))
    add(
        "variant_entry_time_identical",
        int(pair["entry_at_baseline"].ne(pair["entry_at_candidate"]).sum()),
    )
    for column in ("entry_reference_price", "hard_stop_price", "target_price"):
        matches = np.isclose(
            pair[f"{column}_baseline"],
            pair[f"{column}_candidate"],
            rtol=0,
            atol=1e-12,
            equal_nan=False,
        )
        add(f"variant_{column}_identical", int((~matches).sum()))

    activated = candidate[candidate["protection_activated"]]
    add(
        "protection_starts_after_trigger_bar",
        int(
            activated["protection_active_from"]
            .lt(activated["trigger_observed_at"])
            .sum()
        ),
    )
    protected_exits = candidate[
        candidate["exit_reason"].isin(["protected_stop", "protected_stop_gap"])
    ]
    add(
        "protected_exit_requires_prior_activation",
        int(
            protected_exits["protection_active_from"]
            .ge(protected_exits["exit_at"])
            .sum()
            + protected_exits["protection_active_from"].isna().sum()
        ),
    )

    raw_columns = ["signal_id", "model_id", "raw_exit_price", "exit_at", "exit_reason"]
    raw_compare = primary[raw_columns].merge(
        stress[raw_columns],
        on=["signal_id", "model_id"],
        how="outer",
        suffixes=("_primary", "_stress"),
        indicator=True,
        validate="one_to_one",
    )
    add("friction_membership_identical", int(raw_compare["_merge"].ne("both").sum()))
    price_match = np.isclose(
        raw_compare["raw_exit_price_primary"],
        raw_compare["raw_exit_price_stress"],
        rtol=0,
        atol=1e-12,
        equal_nan=False,
    )
    add("friction_raw_exit_identical", int((~price_match).sum()))
    add(
        "friction_exit_time_identical",
        int(raw_compare["exit_at_primary"].ne(raw_compare["exit_at_stress"]).sum()),
    )
    add(
        "friction_exit_reason_identical",
        int(
            raw_compare["exit_reason_primary"]
            .ne(raw_compare["exit_reason_stress"])
            .sum()
        ),
    )
    return failures


def _historical_gate(
    primary_metrics: pd.DataFrame,
    stress_metrics: pd.DataFrame,
    bootstrap: dict[str, Any],
    monthly: pd.DataFrame,
    failures: list[dict[str, Any]],
    signals: pd.DataFrame,
    config: ProjectConfig,
) -> dict[str, Any]:
    primary = primary_metrics.set_index(["model_id", "scope", "value"])
    stress = stress_metrics.set_index(["model_id", "scope", "value"])
    candidate = primary.loc[(CANDIDATE_ID, "overall", "all")]
    baseline = primary.loc[(BASELINE_ID, "overall", "all")]
    stress_candidate = stress.loc[(CANDIDATE_ID, "overall", "all")]
    concentration = _best_month_share(monthly)
    paired_estimate = bootstrap["estimate"]
    ci_lower = bootstrap["ci_lower"]
    checks = {
        "zero_invariant_failures": not failures,
        "exact_parent_membership": (
            len(signals) == config.phase4.parent.expected_signal_count
            and signal_membership_sha256(signals["signal_id"])
            == config.phase4.parent.signal_membership_sha256
        ),
        "positive_mean_trade_net_r": candidate["mean_trade_net_r"] > 0,
        "profit_factor_above_one": (candidate["profit_factor"] or 0) > 1,
        "positive_paired_improvement_over_baseline": (
            paired_estimate is not None and paired_estimate > 0
        ),
        "paired_improvement_ci_lower_above_zero": (
            ci_lower is not None and ci_lower > 0
        ),
        "positive_stress_mean_trade_net_r": (
            stress_candidate["mean_trade_net_r"] > 0
        ),
        "positive_expectancy_each_session": all(
            primary.loc[(CANDIDATE_ID, "session", session)]["mean_trade_net_r"] > 0
            for session in ("london", "new_york")
        ),
        "positive_expectancy_each_direction": all(
            primary.loc[(CANDIDATE_ID, "direction", direction)][
                "mean_trade_net_r"
            ]
            > 0
            for direction in ("long", "short")
        ),
        "lower_maximum_drawdown_than_baseline": (
            candidate["maximum_drawdown_r"] < baseline["maximum_drawdown_r"]
        ),
        "monthly_concentration_within_limit": (
            concentration is not None
            and concentration
            <= config.phase4.historical_gate.maximum_best_month_share_of_positive_r
        ),
    }
    passed = all(bool(value) for value in checks.values())
    return {
        "candidate": CANDIDATE_ID,
        "passed": passed,
        "checks": {key: bool(value) for key, value in checks.items()},
        "paired_improvement": bootstrap,
        "best_month_share_of_positive_r": concentration,
        "action": (
            config.phase4.historical_gate.passed_action
            if passed
            else config.phase4.historical_gate.failed_action
        ),
    }


def _json_default(value: Any) -> Any:
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    if isinstance(value, np.generic):
        return value.item()
    if pd.isna(value):
        return None
    raise TypeError(f"Not JSON serializable: {type(value)!r}")


def run_phase4_historical(
    project_root: Path,
    data_root: Path,
    *,
    artifact_root: Path | None = None,
) -> Phase4Result:
    """Evaluate the sole preregistered management candidate on frozen 2025."""

    config = load_project_config(project_root / "config")
    parent_path = (
        project_root
        / "artifacts"
        / "phase1_1"
        / config.phase4.parent.signal_fingerprint
        / "signals.parquet"
    )
    if not parent_path.is_file():
        raise ValueError(f"Phase 4 parent signal artifact is missing: {parent_path}")

    raw_paths = canonical_m5_paths(data_root, config.research)
    fingerprint, input_hashes = _fingerprint(
        project_root,
        [*raw_paths, parent_path],
    )
    output_parent = (
        artifact_root
        or project_root / "artifacts" / "phase4" / "historical"
    )
    output = output_parent / fingerprint
    output.mkdir(parents=True, exist_ok=True)

    parent_signals = pd.read_parquet(parent_path)
    signals = parent_signals[
        parent_signals["model_id"].eq(config.phase4.parent.signal_model)
        & parent_signals["year"].eq(config.phase4.scope.evaluation_year)
    ].copy()
    signals = signals.sort_values(["decision_at", "signal_id"], kind="stable")
    signals = signals.reset_index(drop=True)

    m5 = load_canonical_m5(data_root, config.research)
    bars = _prepare_bars(m5, config)
    swings, breaks, *_ = _primary_labels(bars, config)
    mappings = attach_structural_stops(
        signals,
        swings["15min"],
        breaks["15min"],
        m5,
        config,
    )
    primary = simulate_management_variants(
        mappings,
        m5,
        config,
        slippage_pips_per_side=(
            config.phase4.execution.primary_slippage_pips_per_side
        ),
    )
    stress = simulate_management_variants(
        mappings,
        m5,
        config,
        slippage_pips_per_side=(
            config.phase4.execution.stress_slippage_pips_per_side
        ),
    )
    primary_metrics = build_metrics(primary)
    stress_metrics = build_metrics(stress)
    paired = _paired_differences(primary)
    bootstrap = _paired_cluster_bootstrap(paired, config)
    monthly = _monthly_summary(primary)
    exits = _exit_summary(primary)
    failures = _invariant_failures(
        signals,
        mappings,
        primary,
        stress,
        config,
    )
    gate = _historical_gate(
        primary_metrics,
        stress_metrics,
        bootstrap,
        monthly,
        failures,
        signals,
        config,
    )

    candidate = primary[primary["model_id"].eq(CANDIDATE_ID)]
    summary = {
        "phase": config.phase4.phase,
        "stage": "historical_2025",
        "fingerprint": fingerprint,
        "parent_signal_fingerprint": config.phase4.parent.signal_fingerprint,
        "evaluation_year": config.phase4.scope.evaluation_year,
        "evidence_role": config.phase4.scope.evidence_role,
        "pristine_program_wide_holdout": False,
        "broker_specific_execution_claim": False,
        "construction_candidate_returns_calculated": False,
        "warmup_year": config.phase4.scope.warmup_year,
        "warmup_role": config.phase4.scope.warmup_role,
        "signal_count": len(signals),
        "signal_membership_sha256": signal_membership_sha256(signals["signal_id"]),
        "valid_structural_mapping_count": int(
            mappings["mapping_status"].eq("valid").sum()
        ),
        "candidate_protection_trigger_count": int(
            candidate["protection_triggered"].sum()
        ),
        "candidate_protection_activation_count": int(
            candidate["protection_activated"].sum()
        ),
        "invariant_failure_count": sum(
            int(item["failure_count"]) for item in failures
        ),
        "invariant_failures": failures,
        "historical_gate": gate,
    }

    signals.to_parquet(output / "signals-frozen-2025.parquet", index=False)
    mappings.to_parquet(output / "structural-stop-mappings.parquet", index=False)
    primary.to_parquet(output / "trades-primary.parquet", index=False)
    stress.to_parquet(output / "trades-stress.parquet", index=False)
    primary_metrics.to_csv(output / "metrics-primary.csv", index=False)
    stress_metrics.to_csv(output / "metrics-stress.csv", index=False)
    paired.to_csv(output / "paired-differences-primary.csv", index=False)
    monthly.to_csv(output / "monthly-primary.csv", index=False)
    exits.to_csv(output / "exit-summary-primary.csv", index=False)
    (output / "bootstrap.json").write_text(
        json.dumps(bootstrap, indent=2, sort_keys=True, default=_json_default) + "\n",
        encoding="utf-8",
    )
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True, default=_json_default) + "\n",
        encoding="utf-8",
    )
    manifest = {
        "phase": config.phase4.phase,
        "stage": "historical_2025",
        "fingerprint": fingerprint,
        "created_at": datetime.now(UTC).isoformat(),
        "parent_signal_fingerprint": config.phase4.parent.signal_fingerprint,
        "input_hashes": input_hashes,
        "config_status": config.phase4.status,
        "artifact_files": sorted(path.name for path in output.iterdir()),
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return Phase4Result(artifact_directory=output, summary=summary)
