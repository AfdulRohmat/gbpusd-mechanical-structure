"""Phase-1.4 causal structural-invalidation stop ablation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml
from pydantic import BaseModel, ConfigDict, Field

from gbpusd_structure.config import ProjectConfig, load_project_config
from gbpusd_structure.data import canonical_m5_paths, load_canonical_m5
from gbpusd_structure.phase0 import _fingerprint, _prepare_bars, _primary_labels

BASELINE_ID = "p3_atr_1_target_2atr"
DIAGNOSTIC_ID = "p3_structure_target_2atr"
CANDIDATE_ID = "p3_structure_target_2r"
STRUCTURAL_IDS = (DIAGNOSTIC_ID, CANDIDATE_ID)


@dataclass(frozen=True)
class Phase14Result:
    artifact_directory: Path
    summary: dict[str, Any]


class Phase14Selection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    phase: str
    stage: str
    status: str
    construction_fingerprint: str = Field(min_length=16, max_length=16)
    parent_fingerprint: str
    selected_candidate: str
    qualified: bool


def load_phase14_selection(path: Path) -> Phase14Selection:
    if not path.is_file():
        raise ValueError(
            "Phase 1.4 replication requires frozen selection file: " f"{path}"
        )
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid Phase 1.4 selection YAML: {exc}") from exc
    selection = Phase14Selection.model_validate(raw)
    expected = {
        "phase": "phase1_4_structural_stop_ablation",
        "stage": "construction_selection",
        "status": "frozen_before_replication",
        "parent_fingerprint": "90d1e369b427d3d8",
        "selected_candidate": CANDIDATE_ID,
        "qualified": True,
    }
    actual = selection.model_dump()
    for key, value in expected.items():
        if actual[key] != value:
            raise ValueError(f"Invalid Phase 1.4 selection field: {key}")
    return selection


def _latest_opposing_swing(
    signal: dict[str, Any],
    swings: pd.DataFrame,
) -> dict[str, Any] | None:
    event_type = "swing_low" if signal["direction"] == "long" else "swing_high"
    decision_at = pd.Timestamp(signal["decision_at"])
    eligible = swings[
        swings["event_type"].eq(event_type)
        & swings["available_at"].le(decision_at)
        & swings["event_at"].lt(decision_at)
        & ~swings["ambiguous_equal"]
    ]
    if eligible.empty:
        return None
    ordered = eligible.sort_values(
        ["confirmation_index", "pivot_index", "event_id"], kind="stable"
    )
    return ordered.iloc[-1].to_dict()


def attach_structural_stops(
    signals: pd.DataFrame,
    swings: pd.DataFrame,
    breaks: pd.DataFrame,
    m5: pd.DataFrame,
    config: ProjectConfig,
) -> pd.DataFrame:
    """Attach causal opposing-swing stop levels to frozen P3 signals."""

    swing_frame = swings[swings["timeframe"].eq("15min")].copy()
    break_frame = breaks[breaks["timeframe"].eq("15min")].copy()
    break_lookup = {
        row["event_id"]: row for row in break_frame.to_dict("records")
    }
    timestamps = pd.to_datetime(m5["timestamp"], utc=True)
    timestamp_values = timestamps.astype("int64").to_numpy()
    rows: list[dict[str, Any]] = []
    buffer_ratio = config.phase1_4.invalidation.buffer_signal_atr
    pip_size = config.research.instrument.pip_size
    fixed_risk = config.phase1_4.risk.fixed_risk_usd
    pip_value = config.phase1_4.risk.usd_per_pip_per_standard_lot

    for signal in signals.to_dict("records"):
        record = dict(signal)
        event = break_lookup.get(signal["source_event_id"])
        source_event_match = bool(
            event is not None
            and event["event_type"] == signal["event_type"]
            and event["available_at"] == signal["decision_at"]
            and (
                (event["direction"] == "up" and signal["direction"] == "long")
                or (
                    event["direction"] == "down"
                    and signal["direction"] == "short"
                )
            )
        )
        swing = _latest_opposing_swing(signal, swing_frame)
        decision_at = pd.Timestamp(signal["decision_at"])
        cutoff_at = pd.Timestamp(signal["cutoff_at"])
        entry_position = int(
            np.searchsorted(timestamp_values, decision_at.value, side="left")
        )
        valid_entry = entry_position < len(m5)
        if valid_entry:
            entry_bar = m5.iloc[entry_position]
            entry_at = pd.Timestamp(entry_bar["timestamp"])
            valid_entry = entry_at >= decision_at and entry_at < cutoff_at
        else:
            entry_at = pd.NaT

        mapping_status = "valid"
        if not source_event_match:
            mapping_status = "source_event_mismatch"
        elif swing is None:
            mapping_status = "missing_opposing_swing"
        elif not valid_entry:
            mapping_status = "missing_entry_bar"

        stop_price = None
        unbuffered_level = None
        reference_entry = None
        stop_distance = None
        swing_bar_count = 0
        if mapping_status == "valid" and swing is not None:
            swing_start = pd.Timestamp(swing["event_at"])
            swing_end = swing_start + pd.Timedelta(15, unit="min")
            in_swing = timestamps.ge(swing_start) & timestamps.lt(swing_end)
            swing_bars = m5[in_swing]
            swing_bar_count = len(swing_bars)
            if swing_bars.empty:
                mapping_status = "missing_swing_execution_bars"
            else:
                atr = float(signal["atr"])
                buffer = buffer_ratio * atr
                if signal["direction"] == "long":
                    reference_entry = float(entry_bar["ask_open"])
                    unbuffered_level = float(swing_bars["bid_low"].min())
                    stop_price = unbuffered_level - buffer
                    stop_distance = reference_entry - stop_price
                else:
                    reference_entry = float(entry_bar["bid_open"])
                    unbuffered_level = float(swing_bars["ask_high"].max())
                    stop_price = unbuffered_level + buffer
                    stop_distance = stop_price - reference_entry
                if not np.isfinite(stop_distance) or stop_distance <= 0:
                    mapping_status = "stop_wrong_side_of_entry"

        if swing is None:
            swing_values: dict[str, Any] = {
                "structural_swing_id": None,
                "structural_swing_type": None,
                "structural_swing_relationship": None,
                "structural_swing_event_at": None,
                "structural_swing_available_at": None,
            }
        else:
            swing_values = {
                "structural_swing_id": swing["event_id"],
                "structural_swing_type": swing["event_type"],
                "structural_swing_relationship": swing[
                    "structural_relationship"
                ],
                "structural_swing_event_at": swing["event_at"],
                "structural_swing_available_at": swing["available_at"],
            }
        risk_pips = (
            None if stop_distance is None else stop_distance / pip_size
        )
        record.update(
            {
                **swing_values,
                "source_event_match": source_event_match,
                "mapping_status": mapping_status,
                "entry_at": entry_at,
                "entry_reference_price": reference_entry,
                "swing_execution_bar_count": swing_bar_count,
                "structural_unbuffered_level": unbuffered_level,
                "structural_buffer_atr": buffer_ratio,
                "structural_stop_price": stop_price,
                "structural_stop_distance": stop_distance,
                "structural_stop_atr": (
                    None
                    if stop_distance is None
                    else stop_distance / float(signal["atr"])
                ),
                "structural_risk_pips": risk_pips,
                "theoretical_lots_at_fixed_risk": (
                    None
                    if risk_pips is None or risk_pips <= 0
                    else fixed_risk / (risk_pips * pip_value)
                ),
            }
        )
        rows.append(record)
    return pd.DataFrame.from_records(rows)


def _simulate_structural_trade(
    setup: dict[str, Any],
    m5: pd.DataFrame,
    config: ProjectConfig,
    *,
    variant_id: str,
    slippage_pips_per_side: float,
) -> dict[str, Any] | None:
    timestamps = pd.to_datetime(m5["timestamp"], utc=True)
    timestamp_values = timestamps.astype("int64").to_numpy()
    entry_position = int(
        np.searchsorted(
            timestamp_values,
            pd.Timestamp(setup["decision_at"]).value,
            side="left",
        )
    )
    cutoff_position = int(
        np.searchsorted(
            timestamp_values,
            pd.Timestamp(setup["cutoff_at"]).value,
            side="left",
        )
    )
    if entry_position >= len(m5) or entry_position >= cutoff_position:
        return None
    if setup["mapping_status"] != "valid":
        return None

    entry_bar = m5.iloc[entry_position]
    entry_at = pd.Timestamp(entry_bar["timestamp"])
    direction = setup["direction"]
    if direction == "long":
        reference_entry = float(entry_bar["ask_open"])
        stop = float(setup["structural_stop_price"])
        stop_distance = reference_entry - stop
    else:
        reference_entry = float(entry_bar["bid_open"])
        stop = float(setup["structural_stop_price"])
        stop_distance = stop - reference_entry
    if stop_distance <= 0:
        return None

    if variant_id == DIAGNOSTIC_ID:
        target_distance = 2.0 * float(setup["atr"])
    elif variant_id == CANDIDATE_ID:
        target_distance = config.phase1_4.risk.target_r * stop_distance
    else:
        raise ValueError(f"Unknown Phase 1.4 structural variant: {variant_id}")
    target = (
        reference_entry + target_distance
        if direction == "long"
        else reference_entry - target_distance
    )

    raw_exit = None
    exit_at = None
    exit_reason = None
    for position in range(entry_position, cutoff_position):
        bar = m5.iloc[position]
        if direction == "long":
            quote_open = float(bar["bid_open"])
            stop_touch = float(bar["bid_low"]) <= stop
            target_touch = float(bar["bid_high"]) >= target
            if quote_open <= stop:
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
            if quote_open >= stop:
                raw_exit, exit_reason = quote_open, "stop_gap"
            elif quote_open <= target:
                raw_exit, exit_reason = target, "target_gap"
            elif stop_touch:
                raw_exit, exit_reason = stop, "stop"
            elif target_touch:
                raw_exit, exit_reason = target, "target"
        if raw_exit is not None:
            exit_at = pd.Timestamp(bar["timestamp"]) + pd.Timedelta(5, unit="min")
            break

    if raw_exit is None:
        final_bar = m5.iloc[cutoff_position - 1]
        raw_exit = float(
            final_bar["bid_close"]
            if direction == "long"
            else final_bar["ask_close"]
        )
        exit_at = min(
            pd.Timestamp(final_bar["timestamp"]) + pd.Timedelta(5, unit="min"),
            pd.Timestamp(setup["cutoff_at"]),
        )
        exit_reason = "time"

    pip_size = config.research.instrument.pip_size
    slip = slippage_pips_per_side * pip_size
    if direction == "long":
        entry_fill = reference_entry + slip
        exit_fill = float(raw_exit) - slip
        pnl_pips_before_commission = (exit_fill - entry_fill) / pip_size
    else:
        entry_fill = reference_entry - slip
        exit_fill = float(raw_exit) + slip
        pnl_pips_before_commission = (entry_fill - exit_fill) / pip_size
    commission_pips = 2 * config.execution.costs.commission_pips_per_side
    net_pips = pnl_pips_before_commission - commission_pips
    risk_pips = stop_distance / pip_size
    net_r = net_pips / risk_pips
    fixed_risk = config.phase1_4.risk.fixed_risk_usd
    pip_value = config.phase1_4.risk.usd_per_pip_per_standard_lot
    return {
        **setup,
        "parent_model_id": setup["model_id"],
        "model_id": variant_id,
        "trade_id": f"trade:{variant_id}:{setup['opportunity_id']}",
        "entry_at": entry_at,
        "exit_at": exit_at,
        "entry_reference_price": reference_entry,
        "entry_fill_price": entry_fill,
        "exit_fill_price": exit_fill,
        "stop_price": stop,
        "target_price": target,
        "target_r_before_costs": target_distance / stop_distance,
        "exit_reason": exit_reason,
        "risk_pips": risk_pips,
        "slippage_pips_per_side": slippage_pips_per_side,
        "commission_pips_round_trip": commission_pips,
        "net_pips": net_pips,
        "net_r": net_r,
        "fixed_risk_usd": fixed_risk,
        "theoretical_lots": fixed_risk / (risk_pips * pip_value),
        "net_usd_at_fixed_risk": net_r * fixed_risk,
        "win": net_pips > 0,
    }


def simulate_structural_variants(
    mappings: pd.DataFrame,
    m5: pd.DataFrame,
    config: ProjectConfig,
    *,
    slippage_pips_per_side: float,
) -> pd.DataFrame:
    rows = []
    for setup in mappings.to_dict("records"):
        for variant_id in STRUCTURAL_IDS:
            trade = _simulate_structural_trade(
                setup,
                m5,
                config,
                variant_id=variant_id,
                slippage_pips_per_side=slippage_pips_per_side,
            )
            if trade is not None:
                rows.append(trade)
    return pd.DataFrame.from_records(rows)


def _baseline_trades(parent: pd.DataFrame) -> pd.DataFrame:
    output = parent.copy()
    output["parent_model_id"] = output["model_id"]
    output["model_id"] = BASELINE_ID
    output["fixed_risk_usd"] = 30.0
    output["net_usd_at_fixed_risk"] = output["net_r"] * 30.0
    output["target_r_before_costs"] = 2.0
    output["theoretical_lots"] = 30.0 / (output["risk_pips"] * 10.0)
    return output


def _profit_factor(values: pd.Series) -> float | None:
    positive = float(values[values.gt(0)].sum())
    negative = abs(float(values[values.lt(0)].sum()))
    return positive / negative if negative else None


def build_metrics(
    trades: pd.DataFrame,
    opportunity_count: int,
) -> pd.DataFrame:
    rows = []
    for model_id in (BASELINE_ID, DIAGNOSTIC_ID, CANDIDATE_ID):
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
                    "period": frame["period"].iloc[0] if len(frame) else None,
                    "scope": scope,
                    "value": value,
                    "opportunity_count": opportunity_count,
                    "trade_count": len(frame),
                    "total_net_r": float(net.sum()),
                    "mean_trade_net_r": float(net.mean()) if len(net) else None,
                    "median_trade_net_r": (
                        float(net.median()) if len(net) else None
                    ),
                    "win_rate": float(frame["win"].mean()) if len(frame) else None,
                    "profit_factor": _profit_factor(net),
                    "mean_opportunity_net_r": (
                        float(net.sum()) / opportunity_count
                        if opportunity_count
                        else None
                    ),
                }
            )
    return pd.DataFrame.from_records(rows)


def _invariant_failures(
    mappings: pd.DataFrame,
    structural_trades: pd.DataFrame,
    parent_trades: pd.DataFrame,
    *,
    period: str,
) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []

    def add(name: str, count: int) -> None:
        if count:
            failures.append({"invariant": name, "failure_count": int(count)})

    add("mapping_count_matches_parent", abs(len(mappings) - len(parent_trades)))
    add("duplicate_mapping_signal", int(mappings["signal_id"].duplicated().sum()))
    add("source_event_reproduced", int((~mappings["source_event_match"]).sum()))
    add("invalid_structural_mapping", int(mappings["mapping_status"].ne("valid").sum()))
    add(
        "swing_available_after_decision",
        int(
            mappings["structural_swing_available_at"]
            .gt(mappings["decision_at"])
            .sum()
        ),
    )
    add(
        "swing_pivot_not_before_decision",
        int(
            mappings["structural_swing_event_at"]
            .ge(mappings["decision_at"])
            .sum()
        ),
    )
    for variant_id in STRUCTURAL_IDS:
        variant = structural_trades[structural_trades["model_id"].eq(variant_id)]
        add(
            f"{variant_id}_trade_count_matches_parent",
            abs(len(variant) - len(parent_trades)),
        )
        duplicates = variant.duplicated(["opportunity_id"], keep=False)
        add(f"{variant_id}_one_trade_per_session", int(duplicates.sum()))

    reference = structural_trades[
        structural_trades["model_id"].eq(CANDIDATE_ID)
    ][["signal_id", "entry_at", "entry_reference_price"]].merge(
        parent_trades[["signal_id", "entry_at", "entry_reference_price"]],
        on="signal_id",
        how="outer",
        suffixes=("_structural", "_parent"),
        indicator=True,
    )
    add("parent_trade_membership", int(reference["_merge"].ne("both").sum()))
    add(
        "entry_timestamp_reproduction",
        int(reference["entry_at_structural"].ne(reference["entry_at_parent"]).sum()),
    )
    price_match = np.isclose(
        reference["entry_reference_price_structural"],
        reference["entry_reference_price_parent"],
        rtol=0,
        atol=1e-12,
        equal_nan=False,
    )
    add("entry_price_reproduction", int((~price_match).sum()))
    wrong_period = int(mappings["period"].ne(period).sum()) + int(
        structural_trades["period"].ne(period).sum()
    )
    add("stage_period_isolation", wrong_period)
    return failures


def _construction_gate(
    metrics: pd.DataFrame,
    failures: list[dict[str, Any]],
) -> dict[str, Any]:
    overall = metrics[metrics["scope"].eq("overall")].set_index("model_id")
    candidate = overall.loc[CANDIDATE_ID]
    baseline = overall.loc[BASELINE_ID]
    conditions = {
        "zero_invariant_failures": not failures,
        "same_trade_count_as_parent": (
            int(candidate["trade_count"]) == int(baseline["trade_count"])
        ),
        "positive_mean_trade_net_r": candidate["mean_trade_net_r"] > 0,
        "profit_factor_above_one": candidate["profit_factor"] > 1,
        "mean_opportunity_improvement_over_parent": (
            candidate["mean_opportunity_net_r"]
            > baseline["mean_opportunity_net_r"]
        ),
    }
    return {
        "candidate": CANDIDATE_ID,
        "conditions": {key: bool(value) for key, value in conditions.items()},
        "passed": all(conditions.values()),
        "action": (
            "freeze_selection_before_replication"
            if all(conditions.values())
            else "stop_without_replication"
        ),
    }


def _stop_distance_summary(mappings: pd.DataFrame) -> pd.DataFrame:
    rows = []
    scopes = [("overall", "all", mappings)]
    scopes.extend(
        ("session", value, mappings[mappings["session"].eq(value)])
        for value in ("london", "new_york")
    )
    scopes.extend(
        ("event_type", value, mappings[mappings["event_type"].eq(value)])
        for value in ("bos", "choch")
    )
    for scope, value, frame in scopes:
        distance = frame["structural_stop_atr"]
        lots = frame["theoretical_lots_at_fixed_risk"]
        rows.append(
            {
                "scope": scope,
                "value": value,
                "count": len(frame),
                "stop_atr_q25": float(distance.quantile(0.25)),
                "stop_atr_median": float(distance.median()),
                "stop_atr_q75": float(distance.quantile(0.75)),
                "stop_atr_q90": float(distance.quantile(0.90)),
                "stop_atr_max": float(distance.max()),
                "theoretical_lots_median": float(lots.median()),
                "theoretical_lots_minimum": float(lots.min()),
            }
        )
    return pd.DataFrame.from_records(rows)


def _json_default(value: Any) -> Any:
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    if isinstance(value, (datetime, pd.Timestamp)):
        return value.isoformat()
    raise TypeError(f"Cannot serialize {type(value).__name__}")


def run_phase1_4_construction(
    project_root: Path,
    data_root: Path,
    *,
    artifact_root: Path | None = None,
) -> Phase14Result:
    """Run construction only; replication stays unavailable pending selection."""

    config = load_project_config(project_root / "config")
    parent = (
        project_root
        / "artifacts"
        / "phase1_1"
        / config.phase1_4.parent.fingerprint
    )
    parent_paths = [
        parent / "signals.parquet",
        parent / "trades-primary.parquet",
        parent / "trades-stress.parquet",
        parent / "opportunities.parquet",
    ]
    for path in parent_paths:
        if not path.is_file():
            raise ValueError(f"Phase 1.4 parent artifact is missing: {path}")

    raw_paths = canonical_m5_paths(data_root, config.research)
    fingerprint, input_hashes = _fingerprint(
        project_root, [*raw_paths, *parent_paths]
    )
    output_parent = (
        artifact_root or project_root / "artifacts" / "phase1_4" / "construction"
    )
    output = output_parent / fingerprint
    output.mkdir(parents=True, exist_ok=True)

    model = config.phase1_4.parent.baseline_model
    year = config.phase1_4.scope.construction_year
    parent_signals = pd.read_parquet(parent_paths[0])
    signals = parent_signals[
        parent_signals["model_id"].eq(model) & parent_signals["year"].eq(year)
    ].copy()
    parent_primary = pd.read_parquet(parent_paths[1])
    parent_primary = parent_primary[
        parent_primary["model_id"].eq(model) & parent_primary["year"].eq(year)
    ].copy()
    parent_stress = pd.read_parquet(parent_paths[2])
    parent_stress = parent_stress[
        parent_stress["model_id"].eq(model) & parent_stress["year"].eq(year)
    ].copy()
    opportunities = pd.read_parquet(parent_paths[3])
    opportunity_count = int(opportunities["year"].eq(year).sum())

    m5 = load_canonical_m5(data_root, config.research)
    bars = _prepare_bars(m5, config)
    swings, breaks, *_ = _primary_labels(bars, config)
    mappings = attach_structural_stops(
        signals, swings["15min"], breaks["15min"], m5, config
    )
    primary_structural = simulate_structural_variants(
        mappings,
        m5,
        config,
        slippage_pips_per_side=(
            config.phase1_4.execution.primary_slippage_pips_per_side
        ),
    )
    stress_structural = simulate_structural_variants(
        mappings,
        m5,
        config,
        slippage_pips_per_side=(
            config.phase1_4.execution.stress_slippage_pips_per_side
        ),
    )
    primary = pd.concat(
        [_baseline_trades(parent_primary), primary_structural],
        ignore_index=True,
        sort=False,
    )
    stress = pd.concat(
        [_baseline_trades(parent_stress), stress_structural],
        ignore_index=True,
        sort=False,
    )
    metrics = build_metrics(primary, opportunity_count)
    stress_metrics = build_metrics(stress, opportunity_count)
    failures = _invariant_failures(
        mappings,
        primary_structural,
        parent_primary,
        period="construction",
    )
    gate = _construction_gate(metrics, failures)
    stop_summary = _stop_distance_summary(mappings)
    summary = {
        "phase": config.phase1_4.phase,
        "stage": "construction",
        "fingerprint": fingerprint,
        "parent_fingerprint": config.phase1_4.parent.fingerprint,
        "construction_year": year,
        "signal_count": len(signals),
        "opportunity_count": opportunity_count,
        "invariant_failure_count": sum(
            int(item["failure_count"]) for item in failures
        ),
        "invariant_failures": failures,
        "construction_gate": gate,
        "replication_permitted": bool(gate["passed"]),
        "replication_returns_calculated": False,
    }

    mappings.to_parquet(output / "structural-stop-mappings.parquet", index=False)
    primary.to_parquet(output / "trades-primary.parquet", index=False)
    stress.to_parquet(output / "trades-stress.parquet", index=False)
    metrics.to_csv(output / "metrics-primary.csv", index=False)
    stress_metrics.to_csv(output / "metrics-stress.csv", index=False)
    stop_summary.to_csv(output / "stop-distance-summary.csv", index=False)
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True, default=_json_default) + "\n",
        encoding="utf-8",
    )
    manifest = {
        "phase": config.phase1_4.phase,
        "stage": "construction",
        "fingerprint": fingerprint,
        "parent_fingerprint": config.phase1_4.parent.fingerprint,
        "created_at": datetime.now(UTC).isoformat(),
        "input_hashes": input_hashes,
        "config_status": config.phase1_4.status,
        "artifact_files": sorted(path.name for path in output.iterdir()),
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return Phase14Result(artifact_directory=output, summary=summary)

