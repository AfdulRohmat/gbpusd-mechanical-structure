"""Phase-3.1 construction outcomes for the frozen trend second-entry sample."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from gbpusd_structure.config import ProjectConfig, load_project_config
from gbpusd_structure.phase0 import _fingerprint, _prepare_bars
from gbpusd_structure.phase1 import build_full_session_opportunities
from gbpusd_structure.phase2 import _load_construction_m5
from gbpusd_structure.phase3 import (
    build_range_setup_candidates,
    build_trend_second_entry_candidates,
    select_session_setups,
)
from gbpusd_structure.price_action import (
    build_m15_price_action_states,
    prepare_m5_bars,
)
from gbpusd_structure.structure import label_swings

MODEL_ID = "with_trend_second_entry_signal_bar_stop_2r"


@dataclass(frozen=True)
class Phase31Result:
    artifact_directory: Path
    summary: dict[str, Any]


def _json_default(value: Any) -> Any:
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    if isinstance(value, np.generic):
        return value.item()
    raise TypeError(f"Cannot serialize {type(value)!r}")


def setup_membership_hash(setups: pd.DataFrame) -> str:
    """Hash the sorted newline-delimited setup identifiers."""

    setup_ids = sorted(setups["setup_id"].astype(str))
    payload = "\n".join(setup_ids) + "\n"
    return hashlib.sha256(payload.encode()).hexdigest()


def rebuild_frozen_setups(
    m5_raw: pd.DataFrame,
    config: ProjectConfig,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Rebuild the complete Phase-3 selection before isolating the frozen family."""

    bars = _prepare_bars(m5_raw, config)
    m15 = bars["15min"]
    swings = label_swings(
        m15,
        config.structure,
        pip_size=config.research.instrument.pip_size,
    )
    states, _, context_events = build_m15_price_action_states(m15, swings, config)
    m5 = prepare_m5_bars(m5_raw, config)
    opportunities = build_full_session_opportunities(m5_raw, config)
    opportunities = opportunities[
        opportunities["year"].eq(config.phase3_1.scope.construction_year)
    ].reset_index(drop=True)
    trend = build_trend_second_entry_candidates(m5, states, opportunities, config)
    ranges = build_range_setup_candidates(
        m5, context_events, states, opportunities, config
    )
    frames = [
        frame.dropna(axis=1, how="all")
        for frame in (trend, ranges)
        if not frame.empty
    ]
    candidates = pd.concat(frames, ignore_index=True, sort=False)
    all_setups = select_session_setups(candidates, config)
    frozen = all_setups[
        all_setups["family"].eq(config.phase3_1.parent.setup_family)
        & all_setups["selected"]
        & all_setups["triggered"]
    ].copy()
    frozen = frozen.sort_values(["triggered_at", "setup_id"], kind="stable")
    return m5, all_setups, frozen.reset_index(drop=True)


def build_execution_mappings(
    setups: pd.DataFrame,
    m5: pd.DataFrame,
    config: ProjectConfig,
) -> pd.DataFrame:
    """Attach causal signal/trigger bars and the frozen signal-bar stop."""

    by_id = m5.set_index("bar_id", drop=False)
    positions = {bar_id: index for index, bar_id in enumerate(m5["bar_id"])}
    pip_size = config.research.instrument.pip_size
    buffer = config.phase3_1.entry_and_bracket.stop_buffer_pips * pip_size
    rows: list[dict[str, Any]] = []

    for setup in setups.to_dict("records"):
        errors: list[str] = []
        signal_id = str(setup["signal_bar_id"])
        trigger_id = str(setup["trigger_bar_id"])
        if signal_id not in by_id.index:
            errors.append("signal_bar_missing")
        if trigger_id not in by_id.index:
            errors.append("trigger_bar_missing")
        if errors:
            rows.append({**setup, "mapping_status": ",".join(errors)})
            continue

        signal = by_id.loc[signal_id]
        trigger = by_id.loc[trigger_id]
        direction = str(setup["direction"])
        trigger_price = float(setup["trigger_price"])
        if direction == "long":
            entry_gap = float(trigger["ask_open"]) >= trigger_price
            entry_reference = max(float(trigger["ask_open"]), trigger_price)
            stop = float(signal["bid_low"]) - buffer
            trigger_touched = float(trigger["ask_high"]) >= trigger_price
            valid_stop = stop < entry_reference
        elif direction == "short":
            entry_gap = float(trigger["bid_open"]) <= trigger_price
            entry_reference = min(float(trigger["bid_open"]), trigger_price)
            stop = float(signal["ask_high"]) + buffer
            trigger_touched = float(trigger["bid_low"]) <= trigger_price
            valid_stop = stop > entry_reference
        else:
            raise ValueError(f"Unknown setup direction: {direction}")

        order_available = pd.Timestamp(setup["available_at"])
        trigger_bar_at = pd.Timestamp(trigger["timestamp"])
        cutoff = pd.Timestamp(setup["cutoff_at"])
        if order_available > trigger_bar_at:
            errors.append("order_available_after_trigger_bar_open")
        if pd.Timestamp(trigger["available_at"]) != pd.Timestamp(
            setup["triggered_at"]
        ):
            errors.append("triggered_at_not_reproduced")
        if not trigger_touched:
            errors.append("trigger_quote_not_touched")
        if trigger_bar_at >= cutoff:
            errors.append("trigger_bar_not_before_cutoff")
        if not valid_stop:
            errors.append("stop_not_beyond_entry")

        risk_price = abs(entry_reference - stop)
        target_r = config.phase3_1.entry_and_bracket.target_r
        target = (
            entry_reference + target_r * risk_price
            if direction == "long"
            else entry_reference - target_r * risk_price
        )
        rows.append(
            {
                **setup,
                "mapping_status": "valid" if not errors else ",".join(errors),
                "signal_bar_at": pd.Timestamp(signal["timestamp"]),
                "trigger_bar_at": trigger_bar_at,
                "trigger_position": positions[trigger_id],
                "entry_gap": entry_gap,
                "entry_reference_price": entry_reference,
                "stop_price": stop,
                "target_price": target,
                "geometric_risk_price": risk_price,
                "risk_pips": risk_price / pip_size,
                "signal_bid_low": float(signal["bid_low"]),
                "signal_ask_high": float(signal["ask_high"]),
                "trigger_quote_touched": trigger_touched,
            }
        )
    return pd.DataFrame.from_records(rows)


def simulate_signal_bar_trade(
    mapping: dict[str, Any],
    m5: pd.DataFrame,
    config: ProjectConfig,
    *,
    slippage_pips_per_side: float,
) -> dict[str, Any] | None:
    """Simulate one stop-entry bracket with conservative entry-bar ordering."""

    if mapping.get("mapping_status") != "valid":
        return None
    start = int(mapping["trigger_position"])
    timestamps = pd.to_datetime(m5["timestamp"], utc=True)
    cutoff = pd.Timestamp(mapping["cutoff_at"])
    end = int(
        np.searchsorted(
            timestamps.astype("int64").to_numpy(), cutoff.value, side="left"
        )
    )
    if start >= end:
        return None

    direction = str(mapping["direction"])
    stop = float(mapping["stop_price"])
    target = float(mapping["target_price"])
    raw_exit: float | None = None
    exit_reason: str | None = None
    exit_position: int | None = None

    for position in range(start, end):
        bar = m5.iloc[position]
        entry_bar = position == start
        entry_gap = bool(mapping["entry_gap"])
        if direction == "long":
            quote_open = float(bar["bid_open"])
            stop_touch = float(bar["bid_low"]) <= stop
            target_touch = float(bar["bid_high"]) >= target
            if entry_bar:
                if entry_gap and quote_open <= stop:
                    raw_exit, exit_reason = quote_open, "stop_gap_entry_bar"
                elif entry_gap and quote_open >= target:
                    raw_exit, exit_reason = target, "target_gap_entry_bar"
                elif stop_touch:
                    raw_exit, exit_reason = stop, "stop_entry_bar_ambiguous"
                elif target_touch:
                    raw_exit, exit_reason = target, "target_entry_bar"
            elif quote_open <= stop:
                raw_exit, exit_reason = quote_open, "stop_gap"
            elif quote_open >= target:
                raw_exit, exit_reason = target, "target_gap"
            elif stop_touch:
                raw_exit, exit_reason = stop, "stop"
            elif target_touch:
                raw_exit, exit_reason = target, "target"
        else:
            quote_open = float(bar["ask_open"])
            stop_touch = float(bar["ask_high"]) >= stop
            target_touch = float(bar["ask_low"]) <= target
            if entry_bar:
                if entry_gap and quote_open >= stop:
                    raw_exit, exit_reason = quote_open, "stop_gap_entry_bar"
                elif entry_gap and quote_open <= target:
                    raw_exit, exit_reason = target, "target_gap_entry_bar"
                elif stop_touch:
                    raw_exit, exit_reason = stop, "stop_entry_bar_ambiguous"
                elif target_touch:
                    raw_exit, exit_reason = target, "target_entry_bar"
            elif quote_open >= stop:
                raw_exit, exit_reason = quote_open, "stop_gap"
            elif quote_open <= target:
                raw_exit, exit_reason = target, "target_gap"
            elif stop_touch:
                raw_exit, exit_reason = stop, "stop"
            elif target_touch:
                raw_exit, exit_reason = target, "target"
        if raw_exit is not None:
            exit_position = position
            break

    if raw_exit is None:
        exit_position = end - 1
        final_bar = m5.iloc[exit_position]
        raw_exit = float(
            final_bar["bid_close"]
            if direction == "long"
            else final_bar["ask_close"]
        )
        exit_reason = "session_cutoff"

    exit_bar = m5.iloc[int(exit_position)]
    exit_at = min(pd.Timestamp(exit_bar["available_at"]), cutoff)
    pip_size = config.research.instrument.pip_size
    slip = slippage_pips_per_side * pip_size
    entry_reference = float(mapping["entry_reference_price"])
    if direction == "long":
        entry_fill = entry_reference + slip
        exit_fill = float(raw_exit) - slip
        gross_pips = (float(raw_exit) - entry_reference) / pip_size
        pips_before_commission = (exit_fill - entry_fill) / pip_size
    else:
        entry_fill = entry_reference - slip
        exit_fill = float(raw_exit) + slip
        gross_pips = (entry_reference - float(raw_exit)) / pip_size
        pips_before_commission = (entry_fill - exit_fill) / pip_size
    commission = 2 * config.phase3_1.execution.commission_pips_per_side
    net_pips = pips_before_commission - commission
    risk_pips = float(mapping["risk_pips"])
    fixed_risk = config.phase3_1.risk.fixed_geometric_risk_usd
    pip_value = config.phase3_1.risk.usd_per_pip_per_standard_lot
    net_r = net_pips / risk_pips
    return {
        **mapping,
        "model_id": MODEL_ID,
        "trade_id": f"trade:{mapping['setup_id']}",
        "entry_bar_at": pd.Timestamp(m5.iloc[start]["timestamp"]),
        "entry_fill_price": entry_fill,
        "exit_bar_at": pd.Timestamp(exit_bar["timestamp"]),
        "exit_at": exit_at,
        "exit_reference_price": float(raw_exit),
        "exit_fill_price": exit_fill,
        "exit_reason": exit_reason,
        "same_entry_bar_exit": int(exit_position) == start,
        "slippage_pips_per_side": slippage_pips_per_side,
        "commission_pips_round_trip": commission,
        "gross_pips": gross_pips,
        "gross_r": gross_pips / risk_pips,
        "net_pips": net_pips,
        "net_r": net_r,
        "fixed_geometric_risk_usd": fixed_risk,
        "theoretical_lots": fixed_risk / (risk_pips * pip_value),
        "net_usd_at_fixed_risk": net_r * fixed_risk,
        "win": net_r > 0,
    }


def simulate_frozen_setups(
    mappings: pd.DataFrame,
    m5: pd.DataFrame,
    config: ProjectConfig,
    *,
    slippage_pips_per_side: float,
) -> pd.DataFrame:
    rows = [
        trade
        for mapping in mappings.to_dict("records")
        if (
            trade := simulate_signal_bar_trade(
                mapping,
                m5,
                config,
                slippage_pips_per_side=slippage_pips_per_side,
            )
        )
        is not None
    ]
    return pd.DataFrame.from_records(rows)


def _profit_factor(values: pd.Series) -> float | None:
    gains = float(values[values.gt(0)].sum())
    losses = abs(float(values[values.lt(0)].sum()))
    return gains / losses if losses else None


def _maximum_drawdown(values: pd.Series) -> float:
    equity = values.cumsum().to_numpy(dtype="float64")
    with_origin = np.concatenate(([0.0], equity))
    peaks = np.maximum.accumulate(with_origin)
    return abs(float((with_origin - peaks).min()))


def build_metrics(trades: pd.DataFrame, execution: str) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    scopes = [("overall", "all", trades)]
    scopes.extend(
        ("session", value, trades[trades["session"].eq(value)])
        for value in ("london", "new_york")
    )
    scopes.extend(
        ("direction", value, trades[trades["direction"].eq(value)])
        for value in ("long", "short")
    )
    for scope, value, frame in scopes:
        ordered = frame.sort_values(["entry_bar_at", "setup_id"], kind="stable")
        net = ordered["net_r"]
        wins = net[net.gt(0)]
        losses = net[net.lt(0)]
        rows.append(
            {
                "model_id": MODEL_ID,
                "execution": execution,
                "scope": scope,
                "value": value,
                "trade_count": len(frame),
                "win_count": int(ordered["win"].sum()),
                "win_rate": float(ordered["win"].mean()) if len(frame) else None,
                "total_net_r": float(net.sum()),
                "mean_trade_net_r": float(net.mean()) if len(frame) else None,
                "median_trade_net_r": float(net.median()) if len(frame) else None,
                "profit_factor": _profit_factor(net),
                "mean_win_r": float(wins.mean()) if len(wins) else None,
                "mean_loss_r": float(losses.mean()) if len(losses) else None,
                "maximum_drawdown_r": _maximum_drawdown(net),
            }
        )
    return pd.DataFrame.from_records(rows)


def build_monthly_metrics(trades: pd.DataFrame) -> pd.DataFrame:
    frame = trades.copy()
    frame["month"] = pd.to_datetime(frame["session_date"]).dt.strftime("%Y-%m")
    rows = []
    for month, monthly in frame.groupby("month", sort=True):
        net = monthly["net_r"]
        rows.append(
            {
                "month": month,
                "trade_count": len(monthly),
                "win_rate": float(monthly["win"].mean()),
                "total_net_r": float(net.sum()),
                "mean_trade_net_r": float(net.mean()),
                "profit_factor": _profit_factor(net),
            }
        )
    return pd.DataFrame.from_records(rows)


def day_cluster_bootstrap(
    trades: pd.DataFrame, config: ProjectConfig
) -> dict[str, Any]:
    settings = config.phase3_1.statistics
    groups = [
        frame["net_r"].to_numpy(dtype="float64")
        for _, frame in trades.groupby("session_date", sort=True)
    ]
    rng = np.random.default_rng(settings.random_seed)
    means = np.empty(settings.bootstrap_resamples, dtype="float64")
    for index in range(settings.bootstrap_resamples):
        sampled = rng.integers(0, len(groups), size=len(groups))
        values = np.concatenate([groups[position] for position in sampled])
        means[index] = values.mean()
    alpha = (1 - settings.confidence_level) / 2
    return {
        "unit": settings.bootstrap_unit,
        "unique_cluster_count": len(groups),
        "resamples": settings.bootstrap_resamples,
        "confidence_level": settings.confidence_level,
        "point_mean_trade_net_r": float(trades["net_r"].mean()),
        "ci_lower": float(np.quantile(means, alpha)),
        "ci_upper": float(np.quantile(means, 1 - alpha)),
    }


def _invariant_failures(
    frozen: pd.DataFrame,
    all_setups: pd.DataFrame,
    mappings: pd.DataFrame,
    primary: pd.DataFrame,
    stress: pd.DataFrame,
    config: ProjectConfig,
) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []

    def add(name: str, count: int) -> None:
        if count:
            failures.append({"invariant": name, "failure_count": int(count)})

    expected_count = config.phase3_1.parent.expected_setup_count
    expected_hash = config.phase3_1.parent.setup_membership_sha256
    add("frozen_setup_count", abs(len(frozen) - expected_count))
    add(
        "frozen_setup_membership_hash",
        int(setup_membership_hash(frozen) != expected_hash),
    )
    add("duplicate_frozen_setup", int(frozen["setup_id"].duplicated().sum()))
    add(
        "non_parent_family_in_frozen_sample",
        int(frozen["family"].ne(config.phase3_1.parent.setup_family).sum()),
    )
    add("unselected_frozen_setup", int((~frozen["selected"]).sum()))
    add("untriggered_frozen_setup", int((~frozen["triggered"]).sum()))
    add(
        "range_outcome_membership",
        int(
            frozen["family"].isin(config.phase3_1.scope.excluded_setup_families).sum()
        ),
    )
    add(
        "construction_year_only",
        int(pd.to_datetime(frozen["session_date"]).dt.year.ne(2024).sum()),
    )
    add("invalid_execution_mapping", int(mappings["mapping_status"].ne("valid").sum()))
    add("primary_trade_count", abs(len(primary) - expected_count))
    add("stress_trade_count", abs(len(stress) - expected_count))
    add("duplicate_primary_trade", int(primary["setup_id"].duplicated().sum()))
    add("duplicate_stress_trade", int(stress["setup_id"].duplicated().sum()))

    selected_counts = (
        all_setups[all_setups["selected"]].groupby("opportunity_id").size()
    )
    sessions = all_setups.drop_duplicates("opportunity_id").set_index("opportunity_id")
    cap_failures = 0
    for opportunity_id, count in selected_counts.items():
        session = sessions.loc[opportunity_id, "session"]
        cap = config.phase3_1.scope.maximum_trades_per_session[session]
        cap_failures += int(count > cap)
    add("parent_session_cap", cap_failures)

    if not primary.empty and not stress.empty:
        joined = primary[
            [
                "setup_id",
                "entry_reference_price",
                "exit_reference_price",
                "stop_price",
                "target_price",
                "exit_reason",
            ]
        ].merge(
            stress[
                [
                    "setup_id",
                    "entry_reference_price",
                    "exit_reference_price",
                    "stop_price",
                    "target_price",
                    "exit_reason",
                ]
            ],
            on="setup_id",
            how="outer",
            suffixes=("_primary", "_stress"),
            indicator=True,
        )
        add("primary_stress_membership", int(joined["_merge"].ne("both").sum()))
        for column in (
            "entry_reference_price",
            "exit_reference_price",
            "stop_price",
            "target_price",
        ):
            equal = np.isclose(
                joined[f"{column}_primary"],
                joined[f"{column}_stress"],
                rtol=0,
                atol=1e-12,
                equal_nan=False,
            )
            add(f"primary_stress_{column}", int((~equal).sum()))
        add(
            "primary_stress_exit_reason",
            int(joined["exit_reason_primary"].ne(joined["exit_reason_stress"]).sum()),
        )
        add("exit_after_cutoff", int(primary["exit_at"].gt(primary["cutoff_at"]).sum()))
    return failures


def _construction_gate(
    metrics: pd.DataFrame,
    monthly: pd.DataFrame,
    bootstrap: dict[str, Any],
    failures: list[dict[str, Any]],
    config: ProjectConfig,
) -> dict[str, Any]:
    primary = metrics[metrics["execution"].eq("primary")]
    stress = metrics[metrics["execution"].eq("stress")]
    overall = primary[primary["scope"].eq("overall")].iloc[0]
    stress_overall = stress[stress["scope"].eq("overall")].iloc[0]
    session = primary[primary["scope"].eq("session")]
    direction = primary[primary["scope"].eq("direction")]
    positive_months = monthly[monthly["total_net_r"].gt(0)]["total_net_r"]
    concentration = (
        float(positive_months.max() / positive_months.sum())
        if len(positive_months)
        else None
    )
    maximum = config.phase3_1.construction_gate.maximum_best_month_share_of_positive_r
    checks = {
        "zero_invariant_failures": not failures,
        "exact_parent_membership": not any(
            item["invariant"]
            in {"frozen_setup_count", "frozen_setup_membership_hash"}
            for item in failures
        ),
        "positive_mean_trade_net_r": float(overall["mean_trade_net_r"]) > 0,
        "profit_factor_above_one": float(overall["profit_factor"] or 0) > 1,
        "positive_stress_mean_trade_net_r": (
            float(stress_overall["mean_trade_net_r"]) > 0
        ),
        "positive_expectancy_each_session": bool(
            session["mean_trade_net_r"].gt(0).all()
        ),
        "positive_expectancy_each_direction": bool(
            direction["mean_trade_net_r"].gt(0).all()
        ),
        "day_cluster_ci_lower_above_zero": float(bootstrap["ci_lower"]) > 0,
        "best_month_concentration_within_limit": (
            concentration is not None and concentration <= maximum
        ),
    }
    passed = all(checks.values())
    return {
        "candidate": MODEL_ID,
        "checks": {key: bool(value) for key, value in checks.items()},
        "passed": passed,
        "best_month_share_of_positive_r": concentration,
        "action": (
            config.phase3_1.construction_gate.passed_action
            if passed
            else config.phase3_1.construction_gate.failed_action
        ),
    }


def run_phase3_1_construction(
    project_root: Path,
    data_root: Path,
    *,
    artifact_root: Path | None = None,
) -> Phase31Result:
    """Open 2024 outcomes for the preregistered Phase-3.1 sample."""

    config = load_project_config(project_root / "config")
    if config.phase3_1.parent.coverage_fingerprint != "c29e50d70f87c916":
        raise ValueError("Unknown Phase 3 coverage parent")
    m5_raw, input_paths = _load_construction_m5(data_root, config)
    if any("2025" in path.name for path in input_paths):
        raise ValueError("Historical replication file opened during Phase 3.1")
    fingerprint, input_hashes = _fingerprint(project_root, input_paths)
    output = (
        artifact_root or project_root / "artifacts" / "phase3_1" / "construction"
    ) / fingerprint
    output.mkdir(parents=True, exist_ok=True)

    m5, all_setups, frozen = rebuild_frozen_setups(m5_raw, config)
    mappings = build_execution_mappings(frozen, m5, config)
    primary = simulate_frozen_setups(
        mappings,
        m5,
        config,
        slippage_pips_per_side=(
            config.phase3_1.execution.primary_slippage_pips_per_side
        ),
    )
    stress = simulate_frozen_setups(
        mappings,
        m5,
        config,
        slippage_pips_per_side=(
            config.phase3_1.execution.stress_slippage_pips_per_side
        ),
    )
    metrics = pd.concat(
        [build_metrics(primary, "primary"), build_metrics(stress, "stress")],
        ignore_index=True,
    )
    monthly = build_monthly_metrics(primary)
    bootstrap = day_cluster_bootstrap(primary, config)
    failures = _invariant_failures(
        frozen, all_setups, mappings, primary, stress, config
    )
    gate = _construction_gate(metrics, monthly, bootstrap, failures, config)
    overall = metrics[
        metrics["execution"].eq("primary") & metrics["scope"].eq("overall")
    ].iloc[0]
    stress_overall = metrics[
        metrics["execution"].eq("stress") & metrics["scope"].eq("overall")
    ].iloc[0]
    exit_counts = {
        str(reason): int(count)
        for reason, count in primary["exit_reason"].value_counts().items()
    }
    summary = {
        "phase": config.phase3_1.phase,
        "fingerprint": fingerprint,
        "parent_coverage_fingerprint": config.phase3_1.parent.coverage_fingerprint,
        "construction_year": config.phase3_1.scope.construction_year,
        "construction_year_is_pristine_holdout": False,
        "historical_replication_files_opened": False,
        "broker_specific_spread_claim": False,
        "opened_input_files": [path.name for path in input_paths],
        "frozen_setup_count": len(frozen),
        "frozen_setup_membership_sha256": setup_membership_hash(frozen),
        "primary": {
            "trade_count": int(overall["trade_count"]),
            "win_rate": overall["win_rate"],
            "mean_trade_net_r": overall["mean_trade_net_r"],
            "total_net_r": overall["total_net_r"],
            "profit_factor": overall["profit_factor"],
            "maximum_drawdown_r": overall["maximum_drawdown_r"],
            "same_entry_bar_exit_count": int(primary["same_entry_bar_exit"].sum()),
            "exit_counts": exit_counts,
        },
        "stress": {
            "mean_trade_net_r": stress_overall["mean_trade_net_r"],
            "total_net_r": stress_overall["total_net_r"],
            "profit_factor": stress_overall["profit_factor"],
        },
        "day_cluster_bootstrap": bootstrap,
        "invariant_failure_count": len(failures),
        "invariant_failures": failures,
        "construction_gate": gate,
        "external_validation_permitted": bool(gate["passed"] and not failures),
        "decision": gate["action"],
    }

    frozen.to_parquet(output / "frozen-setups.parquet", index=False)
    mappings.to_parquet(output / "execution-mappings.parquet", index=False)
    primary.to_parquet(output / "trades-primary.parquet", index=False)
    stress.to_parquet(output / "trades-stress.parquet", index=False)
    metrics.to_csv(output / "metrics.csv", index=False)
    monthly.to_csv(output / "monthly.csv", index=False)
    (output / "bootstrap.json").write_text(
        json.dumps(bootstrap, indent=2, sort_keys=True, default=_json_default) + "\n",
        encoding="utf-8",
    )
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True, default=_json_default) + "\n",
        encoding="utf-8",
    )
    manifest = {
        "phase": config.phase3_1.phase,
        "fingerprint": fingerprint,
        "created_at": datetime.now(UTC).isoformat(),
        "input_hashes": input_hashes,
        "historical_replication_files_opened": False,
        "broker_specific_spread_claim": False,
        "artifact_files": sorted(path.name for path in output.iterdir()),
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return Phase31Result(artifact_directory=output, summary=summary)
