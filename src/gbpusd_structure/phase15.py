"""Phase-1.5 coverage-only FVG pullback entry funnel."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from gbpusd_structure.config import ProjectConfig, load_project_config
from gbpusd_structure.data import canonical_m5_paths, load_canonical_m5
from gbpusd_structure.m1 import load_m1_year, m1_month_path, reconcile_m1_to_m5
from gbpusd_structure.phase0 import _fingerprint

E0 = "e0_immediate_structure_2atr"
E1 = "e1_m5_fvg_mitigation"
E2 = "e2_m5_fvg_m1_refinement"
CANDIDATES = (E1, E2)

COVERAGE_COLUMNS = (
    "model_id",
    "signal_id",
    "opportunity_id",
    "session",
    "session_date",
    "year",
    "period",
    "direction",
    "event_type",
    "signal_decision_at",
    "cutoff_at",
    "structural_mapping_status",
    "coverage_status",
    "m5_fvg_id",
    "m5_fvg_available_at",
    "m5_mitigation_bar_at",
    "m1_fvg_id",
    "m1_fvg_available_at",
    "entry_decision_at",
    "entry_at",
)


@dataclass(frozen=True)
class Phase15Result:
    artifact_directory: Path
    summary: dict[str, Any]


def label_lower_timeframe_fvgs(
    bars: pd.DataFrame,
    *,
    timeframe: str,
    minutes: int,
    atr_period: int,
    minimum_size_atr: float,
) -> pd.DataFrame:
    """Label causal, contiguous three-candle Bid/Ask-independent mid FVGs."""

    frame = bars.sort_values("timestamp", kind="stable").reset_index(drop=True).copy()
    timestamp = pd.to_datetime(frame["timestamp"], utc=True)
    previous_close = frame["mid_close"].shift(1)
    true_range = pd.concat(
        [
            frame["mid_high"] - frame["mid_low"],
            (frame["mid_high"] - previous_close).abs(),
            (frame["mid_low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr = true_range.rolling(atr_period, min_periods=atr_period).mean()
    duration = pd.Timedelta(minutes, unit="min")
    contiguous = timestamp.diff().eq(duration) & timestamp.diff().shift(1).eq(duration)
    first_at = timestamp.shift(2)
    first_high = frame["mid_high"].shift(2)
    first_low = frame["mid_low"].shift(2)
    bullish_size = frame["mid_low"] - first_high
    bearish_size = first_low - frame["mid_high"]
    minimum = minimum_size_atr * atr
    rows = []
    definitions = (
        (
            "long",
            bullish_size,
            first_high,
            frame["mid_low"],
        ),
        (
            "short",
            bearish_size,
            frame["mid_high"],
            first_low,
        ),
    )
    for direction, size, lower, upper in definitions:
        mask = contiguous & atr.notna() & size.ge(minimum) & size.gt(0)
        selected = pd.DataFrame(
            {
                "timeframe": timeframe,
                "direction": direction,
                "first_bar_at": first_at[mask],
                "third_bar_at": timestamp[mask],
                "available_at": timestamp[mask] + duration,
                "lower_bound": lower[mask].astype("float64"),
                "upper_bound": upper[mask].astype("float64"),
                "size": size[mask].astype("float64"),
                "atr": atr[mask].astype("float64"),
            }
        )
        selected["fvg_id"] = [
            f"fvg:{timeframe}:{direction}:{pd.Timestamp(value).isoformat()}"
            for value in selected["third_bar_at"]
        ]
        rows.append(selected)
    output = pd.concat(rows, ignore_index=True)
    return output.sort_values(["available_at", "fvg_id"], kind="stable").reset_index(
        drop=True
    )


def _first_fvg(
    fvgs: pd.DataFrame,
    *,
    direction: str,
    available_from: pd.Timestamp,
    available_before: pd.Timestamp,
) -> dict[str, Any] | None:
    eligible = fvgs[
        fvgs["direction"].eq(direction)
        & fvgs["available_at"].ge(available_from)
        & fvgs["available_at"].lt(available_before)
    ]
    return None if eligible.empty else eligible.iloc[0].to_dict()


def _resolution(
    bar: dict[str, Any],
    *,
    direction: str,
    stop: float,
    target: float,
) -> str | None:
    if direction == "long":
        if float(bar["bid_low"]) <= stop:
            return "stop_before_entry"
        if float(bar["bid_high"]) >= target:
            return "target_before_entry"
    else:
        if float(bar["ask_high"]) >= stop:
            return "stop_before_entry"
        if float(bar["ask_low"]) <= target:
            return "target_before_entry"
    return None


def _mitigated(
    bar: dict[str, Any],
    *,
    direction: str,
    fvg: dict[str, Any],
) -> bool:
    if direction == "long":
        return float(bar["ask_low"]) <= float(fvg["upper_bound"])
    return float(bar["bid_high"]) >= float(fvg["lower_bound"])


def _valid_entry(
    price: float,
    *,
    direction: str,
    stop: float,
    target: float,
) -> bool:
    if direction == "long":
        return stop < price < target
    return target < price < stop


def _base_coverage_record(
    mapping: dict[str, Any],
    model_id: str,
) -> dict[str, Any]:
    return {
        "model_id": model_id,
        "signal_id": mapping["signal_id"],
        "opportunity_id": mapping["opportunity_id"],
        "session": mapping["session"],
        "session_date": mapping["session_date"],
        "year": mapping["year"],
        "period": mapping["period"],
        "direction": mapping["direction"],
        "event_type": mapping["event_type"],
        "signal_decision_at": mapping["decision_at"],
        "cutoff_at": mapping["cutoff_at"],
        "structural_mapping_status": mapping["mapping_status"],
        "coverage_status": None,
        "m5_fvg_id": None,
        "m5_fvg_available_at": None,
        "m5_mitigation_bar_at": None,
        "m1_fvg_id": None,
        "m1_fvg_available_at": None,
        "entry_decision_at": None,
        "entry_at": None,
    }


def _price_geometry(mapping: dict[str, Any]) -> tuple[float, float]:
    stop = float(mapping["structural_stop_price"])
    parent_entry = float(mapping["entry_reference_price"])
    target = (
        parent_entry + 2.0 * float(mapping["atr"])
        if mapping["direction"] == "long"
        else parent_entry - 2.0 * float(mapping["atr"])
    )
    return stop, target


def _m5_entry_coverage(
    mapping: dict[str, Any],
    m5: pd.DataFrame,
    m5_fvgs: pd.DataFrame,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    record = _base_coverage_record(mapping, E1)
    if mapping["mapping_status"] != "valid":
        record["coverage_status"] = "invalid_parent_mapping"
        return record, None
    direction = mapping["direction"]
    decision = pd.Timestamp(mapping["decision_at"])
    cutoff = pd.Timestamp(mapping["cutoff_at"])
    fvg = _first_fvg(
        m5_fvgs,
        direction=direction,
        available_from=decision,
        available_before=cutoff,
    )
    if fvg is None:
        record["coverage_status"] = "no_directional_m5_fvg"
        return record, None
    record["m5_fvg_id"] = fvg["fvg_id"]
    record["m5_fvg_available_at"] = fvg["available_at"]
    stop, target = _price_geometry(mapping)
    path = m5[
        m5["timestamp"].ge(fvg["available_at"])
        & m5["timestamp"].lt(cutoff)
    ]
    mitigation_at = None
    for bar in path.to_dict("records"):
        resolution = _resolution(
            bar, direction=direction, stop=stop, target=target
        )
        if resolution is not None:
            record["coverage_status"] = resolution
            return record, fvg
        if _mitigated(bar, direction=direction, fvg=fvg):
            mitigation_at = pd.Timestamp(bar["timestamp"])
            break
    if mitigation_at is None:
        record["coverage_status"] = "no_m5_mitigation_before_cutoff"
        return record, fvg
    record["m5_mitigation_bar_at"] = mitigation_at
    entry_decision = mitigation_at + pd.Timedelta(5, unit="min")
    entries = m5[
        m5["timestamp"].ge(entry_decision) & m5["timestamp"].lt(cutoff)
    ]
    if entries.empty:
        record["coverage_status"] = "no_m5_entry_before_cutoff"
        return record, fvg
    entry = entries.iloc[0]
    entry_price = float(
        entry["ask_open"] if direction == "long" else entry["bid_open"]
    )
    if not _valid_entry(
        entry_price, direction=direction, stop=stop, target=target
    ):
        record["coverage_status"] = "entry_outside_stop_target"
        return record, fvg
    record.update(
        {
            "coverage_status": "entry",
            "entry_decision_at": entry_decision,
            "entry_at": pd.Timestamp(entry["timestamp"]),
        }
    )
    return record, fvg


def _overlaps(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return max(float(left["lower_bound"]), float(right["lower_bound"])) < min(
        float(left["upper_bound"]), float(right["upper_bound"])
    )


def _m1_entry_coverage(
    mapping: dict[str, Any],
    m1: pd.DataFrame,
    m5_fvg: dict[str, Any] | None,
    m1_fvgs: pd.DataFrame,
) -> dict[str, Any]:
    record = _base_coverage_record(mapping, E2)
    if mapping["mapping_status"] != "valid":
        record["coverage_status"] = "invalid_parent_mapping"
        return record
    if m5_fvg is None:
        record["coverage_status"] = "no_directional_m5_fvg"
        return record
    record["m5_fvg_id"] = m5_fvg["fvg_id"]
    record["m5_fvg_available_at"] = m5_fvg["available_at"]
    direction = mapping["direction"]
    cutoff = pd.Timestamp(mapping["cutoff_at"])
    stop, target = _price_geometry(mapping)
    path = m1[
        m1["timestamp"].ge(m5_fvg["available_at"])
        & m1["timestamp"].lt(cutoff)
    ]
    mitigation_at = None
    for bar in path.to_dict("records"):
        resolution = _resolution(
            bar, direction=direction, stop=stop, target=target
        )
        if resolution is not None:
            record["coverage_status"] = resolution
            return record
        if _mitigated(bar, direction=direction, fvg=m5_fvg):
            mitigation_at = pd.Timestamp(bar["timestamp"])
            break
    if mitigation_at is None:
        record["coverage_status"] = "no_m1_mitigation_before_cutoff"
        return record
    record["m5_mitigation_bar_at"] = mitigation_at
    mitigation_available = mitigation_at + pd.Timedelta(1, unit="min")
    nested = m1_fvgs[
        m1_fvgs["direction"].eq(direction)
        & m1_fvgs["first_bar_at"].ge(mitigation_available)
        & m1_fvgs["available_at"].lt(cutoff)
    ]
    if not nested.empty:
        nested = nested[
            nested.apply(
                lambda row: _overlaps(row.to_dict(), m5_fvg), axis=1
            )
        ]
    if nested.empty:
        record["coverage_status"] = "no_nested_m1_fvg_before_cutoff"
        return record
    m1_fvg = nested.iloc[0].to_dict()
    record["m1_fvg_id"] = m1_fvg["fvg_id"]
    record["m1_fvg_available_at"] = m1_fvg["available_at"]
    before_entry = path[
        path["timestamp"].ge(mitigation_available)
        & path["timestamp"].lt(m1_fvg["available_at"])
    ]
    for bar in before_entry.to_dict("records"):
        resolution = _resolution(
            bar, direction=direction, stop=stop, target=target
        )
        if resolution is not None:
            record["coverage_status"] = resolution
            return record
    entry_decision = pd.Timestamp(m1_fvg["available_at"])
    entries = m1[
        m1["timestamp"].ge(entry_decision) & m1["timestamp"].lt(cutoff)
    ]
    if entries.empty:
        record["coverage_status"] = "no_m1_entry_before_cutoff"
        return record
    entry = entries.iloc[0]
    resolution = _resolution(
        entry.to_dict(), direction=direction, stop=stop, target=target
    )
    if resolution is not None:
        record["coverage_status"] = resolution
        return record
    entry_price = float(
        entry["ask_open"] if direction == "long" else entry["bid_open"]
    )
    if not _valid_entry(
        entry_price, direction=direction, stop=stop, target=target
    ):
        record["coverage_status"] = "entry_outside_stop_target"
        return record
    record.update(
        {
            "coverage_status": "entry",
            "entry_decision_at": entry_decision,
            "entry_at": pd.Timestamp(entry["timestamp"]),
        }
    )
    return record


def build_coverage_funnel(
    mappings: pd.DataFrame,
    m5: pd.DataFrame,
    m1: pd.DataFrame,
    m5_fvgs: pd.DataFrame,
    m1_fvgs: pd.DataFrame,
) -> pd.DataFrame:
    records = []
    for mapping in mappings.sort_values("decision_at", kind="stable").to_dict(
        "records"
    ):
        baseline = _base_coverage_record(mapping, E0)
        if mapping["mapping_status"] == "valid":
            baseline.update(
                {
                    "coverage_status": "entry",
                    "entry_decision_at": mapping["decision_at"],
                    "entry_at": mapping["entry_at"],
                }
            )
        else:
            baseline["coverage_status"] = "invalid_parent_mapping"
        records.append(baseline)
        e1, m5_fvg = _m5_entry_coverage(mapping, m5, m5_fvgs)
        records.append(e1)
        records.append(_m1_entry_coverage(mapping, m1, m5_fvg, m1_fvgs))
    return pd.DataFrame.from_records(records, columns=COVERAGE_COLUMNS)


def _coverage_invariant_failures(coverage: pd.DataFrame) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []

    def add(name: str, count: int) -> None:
        if count:
            failures.append({"invariant": name, "failure_count": int(count)})

    banned = {
        "net_r",
        "net_pips",
        "pnl",
        "win",
        "profit_factor",
        "exit_price",
        "return",
    }
    add("coverage_return_columns_forbidden", len(banned.intersection(coverage.columns)))
    add(
        "duplicate_model_opportunity",
        int(coverage.duplicated(["model_id", "opportunity_id"]).sum()),
    )
    entries = coverage[coverage["coverage_status"].eq("entry")]
    add(
        "entry_before_decision",
        int(entries["entry_at"].lt(entries["entry_decision_at"]).sum()),
    )
    add(
        "entry_at_or_after_cutoff",
        int(entries["entry_at"].ge(entries["cutoff_at"]).sum()),
    )
    add("non_construction_row", int(coverage["period"].ne("construction").sum()))
    e1 = entries[entries["model_id"].eq(E1)]
    if not e1.empty:
        add(
            "e1_mitigation_before_fvg_available",
            int(e1["m5_mitigation_bar_at"].lt(e1["m5_fvg_available_at"]).sum()),
        )
    e2 = entries[entries["model_id"].eq(E2)]
    if not e2.empty:
        add(
            "e2_refinement_before_mitigation",
            int(
                e2["m1_fvg_available_at"].le(e2["m5_mitigation_bar_at"]).sum()
            ),
        )
    return failures


def _coverage_summary(
    coverage: pd.DataFrame,
    config: ProjectConfig,
) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    counts = (
        coverage.groupby(["model_id", "coverage_status"], sort=True)
        .size()
        .rename("signal_count")
        .reset_index()
    )
    entries = coverage[coverage["coverage_status"].eq("entry")].copy()
    entries["month"] = (
        pd.to_datetime(entries["session_date"]).dt.to_period("M").astype(str)
    )
    monthly = (
        entries.groupby(["model_id", "month"], sort=True)
        .size()
        .rename("entry_count")
        .reset_index()
    )
    minimum = config.phase1_5.coverage_stage.minimum_evaluable_trades_per_year
    eligible = [
        model_id
        for model_id in CANDIDATES
        if int(entries["model_id"].eq(model_id).sum()) >= minimum
    ]
    return counts, monthly, eligible


def run_phase1_5_coverage(
    project_root: Path,
    data_root: Path,
    *,
    artifact_root: Path | None = None,
) -> Phase15Result:
    """Run construction entry coverage without accessing strategy returns."""

    config = load_project_config(project_root / "config")
    year = config.phase1_5.scope.construction_year
    parent = (
        project_root
        / "artifacts"
        / "phase1_4"
        / "construction"
        / config.phase1_5.parent.structural_construction_fingerprint
    )
    mapping_path = parent / "structural-stop-mappings.parquet"
    if not mapping_path.is_file():
        raise ValueError(f"Phase 1.5 parent mapping is missing: {mapping_path}")
    m1_paths = [
        m1_month_path(data_root, config.research.instrument.symbol, year, month)
        for month in range(1, 13)
    ]
    missing_m1 = [str(path) for path in m1_paths if not path.is_file()]
    if missing_m1:
        raise ValueError("Phase 1.5 M1 build is incomplete: " + ", ".join(missing_m1))
    m5_paths = canonical_m5_paths(data_root, config.research)
    fingerprint, input_hashes = _fingerprint(
        project_root, [*m5_paths, *m1_paths, mapping_path]
    )
    output_parent = (
        artifact_root or project_root / "artifacts" / "phase1_5" / "coverage"
    )
    output = output_parent / fingerprint
    output.mkdir(parents=True, exist_ok=True)

    mappings = pd.read_parquet(mapping_path)
    mappings = mappings[mappings["year"].eq(year)].copy()
    m5_all = load_canonical_m5(data_root, config.research)
    m5 = m5_all[m5_all["timestamp"].dt.year.eq(year)].reset_index(drop=True)
    m1 = load_m1_year(data_root, config, year)
    reconciliation = reconcile_m1_to_m5(m1, m5)
    if not reconciliation["valid"]:
        raise ValueError(f"Phase 1.5 M1 reconciliation failed: {reconciliation}")

    settings = config.phase1_5.fvg
    m5_fvgs = label_lower_timeframe_fvgs(
        m5,
        timeframe="5min",
        minutes=5,
        atr_period=settings.atr_period,
        minimum_size_atr=settings.minimum_size_atr,
    )
    m1_fvgs = label_lower_timeframe_fvgs(
        m1,
        timeframe="1min",
        minutes=1,
        atr_period=settings.atr_period,
        minimum_size_atr=settings.minimum_size_atr,
    )
    coverage = build_coverage_funnel(mappings, m5, m1, m5_fvgs, m1_fvgs)
    failures = _coverage_invariant_failures(coverage)
    counts, monthly, eligible = _coverage_summary(coverage, config)
    desired_min, desired_max = config.phase1_5.coverage_stage.desired_trades_per_year
    entry_counts = {
        model_id: int(
            (
                coverage["model_id"].eq(model_id)
                & coverage["coverage_status"].eq("entry")
            ).sum()
        )
        for model_id in (E0, E1, E2)
    }
    summary = {
        "phase": config.phase1_5.phase,
        "stage": "construction_coverage_only",
        "fingerprint": fingerprint,
        "parent_fingerprint": (
            config.phase1_5.parent.structural_construction_fingerprint
        ),
        "returns_accessed": False,
        "m1_reconciliation": reconciliation,
        "m5_fvg_count": len(m5_fvgs),
        "m1_fvg_count": len(m1_fvgs),
        "entry_counts": entry_counts,
        "mean_entries_per_month": {
            model_id: count / 12 for model_id, count in entry_counts.items()
        },
        "minimum_evaluable_count": (
            config.phase1_5.coverage_stage.minimum_evaluable_trades_per_year
        ),
        "desired_coverage_range": [desired_min, desired_max],
        "desired_coverage_met": {
            model_id: desired_min <= count <= desired_max
            for model_id, count in entry_counts.items()
        },
        "eligible_candidates": eligible,
        "invariant_failure_count": sum(
            int(item["failure_count"]) for item in failures
        ),
        "invariant_failures": failures,
        "construction_pnl_permitted": bool(eligible and not failures),
    }

    coverage.to_parquet(output / "coverage-signals.parquet", index=False)
    counts.to_csv(output / "coverage-counts.csv", index=False)
    monthly.to_csv(output / "monthly-entry-counts.csv", index=False)
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    manifest = {
        "phase": config.phase1_5.phase,
        "stage": "construction_coverage_only",
        "fingerprint": fingerprint,
        "created_at": datetime.now(UTC).isoformat(),
        "input_hashes": input_hashes,
        "config_status": config.phase1_5.status,
        "artifact_files": sorted(path.name for path in output.iterdir()),
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return Phase15Result(artifact_directory=output, summary=summary)


def _simulate_delayed_trade(
    coverage: dict[str, Any],
    mapping: dict[str, Any],
    bars: pd.DataFrame,
    config: ProjectConfig,
    *,
    slippage_pips_per_side: float,
) -> dict[str, Any] | None:
    timestamps = pd.to_datetime(bars["timestamp"], utc=True)
    timestamp_values = timestamps.astype("int64").to_numpy()
    entry_position = int(
        np.searchsorted(
            timestamp_values,
            pd.Timestamp(coverage["entry_at"]).value,
            side="left",
        )
    )
    cutoff_position = int(
        np.searchsorted(
            timestamp_values,
            pd.Timestamp(mapping["cutoff_at"]).value,
            side="left",
        )
    )
    if entry_position >= len(bars) or entry_position >= cutoff_position:
        return None
    entry_bar = bars.iloc[entry_position]
    entry_at = pd.Timestamp(entry_bar["timestamp"])
    if entry_at != pd.Timestamp(coverage["entry_at"]):
        return None

    direction = mapping["direction"]
    stop, target = _price_geometry(mapping)
    if direction == "long":
        reference_entry = float(entry_bar["ask_open"])
        risk_distance = reference_entry - stop
        target_distance = target - reference_entry
    else:
        reference_entry = float(entry_bar["bid_open"])
        risk_distance = stop - reference_entry
        target_distance = reference_entry - target
    if risk_distance <= 0 or target_distance <= 0:
        return None

    raw_exit = None
    exit_at = None
    exit_reason = None
    for position in range(entry_position, cutoff_position):
        bar = bars.iloc[position]
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
            resolution_minutes = 5 if coverage["model_id"] == E1 else 1
            exit_at = pd.Timestamp(bar["timestamp"]) + pd.Timedelta(
                resolution_minutes, unit="min"
            )
            break

    if raw_exit is None:
        final_bar = bars.iloc[cutoff_position - 1]
        raw_exit = float(
            final_bar["bid_close"]
            if direction == "long"
            else final_bar["ask_close"]
        )
        resolution_minutes = 5 if coverage["model_id"] == E1 else 1
        exit_at = min(
            pd.Timestamp(final_bar["timestamp"])
            + pd.Timedelta(resolution_minutes, unit="min"),
            pd.Timestamp(mapping["cutoff_at"]),
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
    commission_pips = 2 * config.phase1_5.execution.commission_pips_per_side
    net_pips = pnl_pips_before_commission - commission_pips
    risk_pips = risk_distance / pip_size
    net_r = net_pips / risk_pips
    fixed_risk = config.phase1_5.execution.fixed_risk_usd
    pip_value = config.phase1_4.risk.usd_per_pip_per_standard_lot
    return {
        **mapping,
        "parent_model_id": mapping["model_id"],
        "model_id": coverage["model_id"],
        "trade_id": f"trade:{coverage['model_id']}:{mapping['opportunity_id']}",
        "fvg_entry_decision_at": coverage["entry_decision_at"],
        "m5_fvg_id": coverage["m5_fvg_id"],
        "m5_fvg_available_at": coverage["m5_fvg_available_at"],
        "m5_mitigation_bar_at": coverage["m5_mitigation_bar_at"],
        "m1_fvg_id": coverage["m1_fvg_id"],
        "m1_fvg_available_at": coverage["m1_fvg_available_at"],
        "entry_at": entry_at,
        "exit_at": exit_at,
        "entry_reference_price": reference_entry,
        "entry_fill_price": entry_fill,
        "exit_fill_price": exit_fill,
        "stop_price": stop,
        "target_price": target,
        "target_r_before_costs": target_distance / risk_distance,
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


def simulate_delayed_entries(
    coverage: pd.DataFrame,
    mappings: pd.DataFrame,
    m5: pd.DataFrame,
    m1: pd.DataFrame,
    config: ProjectConfig,
    *,
    slippage_pips_per_side: float,
) -> pd.DataFrame:
    mapping_lookup = {
        row["signal_id"]: row for row in mappings.to_dict("records")
    }
    rows = []
    entries = coverage[coverage["coverage_status"].eq("entry")]
    for candidate in entries.to_dict("records"):
        mapping = mapping_lookup[candidate["signal_id"]]
        bars = m5 if candidate["model_id"] == E1 else m1
        trade = _simulate_delayed_trade(
            candidate,
            mapping,
            bars,
            config,
            slippage_pips_per_side=slippage_pips_per_side,
        )
        if trade is not None:
            rows.append(trade)
    return pd.DataFrame.from_records(rows)


def _baseline_e0(parent: pd.DataFrame) -> pd.DataFrame:
    output = parent.copy()
    output["parent_model_id"] = output["model_id"]
    output["model_id"] = E0
    return output


def _profit_factor(values: pd.Series) -> float | None:
    positive = float(values[values.gt(0)].sum())
    negative = abs(float(values[values.lt(0)].sum()))
    return positive / negative if negative else None


def _construction_metrics(
    trades: pd.DataFrame,
    opportunity_count: int,
) -> pd.DataFrame:
    rows = []
    for model_id in (E0, E1, E2):
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
            target_r = frame["target_r_before_costs"]
            rows.append(
                {
                    "model_id": model_id,
                    "period": "construction",
                    "scope": scope,
                    "value": value,
                    "opportunity_count": opportunity_count,
                    "trade_count": len(frame),
                    "total_net_r": float(net.sum()),
                    "mean_trade_net_r": float(net.mean()) if len(net) else None,
                    "median_trade_net_r": float(net.median()) if len(net) else None,
                    "win_rate": float(frame["win"].mean()) if len(frame) else None,
                    "profit_factor": _profit_factor(net),
                    "mean_opportunity_net_r": (
                        float(net.sum()) / opportunity_count
                        if opportunity_count
                        else None
                    ),
                    "median_target_r_before_costs": (
                        float(target_r.median()) if len(target_r) else None
                    ),
                    "median_risk_pips": (
                        float(frame["risk_pips"].median()) if len(frame) else None
                    ),
                }
            )
    return pd.DataFrame.from_records(rows)


def _construction_invariant_failures(
    coverage: pd.DataFrame,
    mappings: pd.DataFrame,
    candidate_trades: pd.DataFrame,
    baseline: pd.DataFrame,
    config: ProjectConfig,
) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []

    def add(name: str, count: int) -> None:
        if count:
            failures.append({"invariant": name, "failure_count": int(count)})

    frozen_counts = {
        item.id: item.entry_count
        for item in config.phase1_5_coverage_selection.eligible_candidates
    }
    for model_id, expected in frozen_counts.items():
        actual = int(candidate_trades["model_id"].eq(model_id).sum())
        add(f"{model_id}_trade_count_matches_coverage", abs(actual - expected))
    add("baseline_trade_count", abs(len(baseline) - 384))
    add(
        "duplicate_candidate_trade",
        int(candidate_trades.duplicated(["model_id", "opportunity_id"]).sum()),
    )
    add(
        "non_construction_trade",
        int(candidate_trades["period"].ne("construction").sum()),
    )
    add(
        "entry_at_or_after_cutoff",
        int(candidate_trades["entry_at"].ge(candidate_trades["cutoff_at"]).sum()),
    )
    add(
        "nonpositive_risk",
        int(candidate_trades["risk_pips"].le(0).sum()),
    )
    add(
        "nonpositive_target_r",
        int(candidate_trades["target_r_before_costs"].le(0).sum()),
    )
    entry_reference = coverage[coverage["coverage_status"].eq("entry")][
        ["model_id", "signal_id", "entry_at"]
    ].merge(
        candidate_trades[["model_id", "signal_id", "entry_at"]],
        on=["model_id", "signal_id"],
        how="outer",
        suffixes=("_coverage", "_trade"),
        indicator=True,
    )
    add("coverage_trade_membership", int(entry_reference["_merge"].ne("both").sum()))
    add(
        "coverage_entry_reproduction",
        int(entry_reference["entry_at_coverage"].ne(entry_reference["entry_at_trade"]).sum()),
    )
    mapping_lookup = mappings.set_index("signal_id")
    expected_targets = []
    for row in candidate_trades.to_dict("records"):
        mapping = mapping_lookup.loc[row["signal_id"]]
        _, target = _price_geometry(mapping.to_dict())
        expected_targets.append(target)
    target_match = np.isclose(
        candidate_trades["target_price"],
        expected_targets,
        rtol=0,
        atol=1e-12,
        equal_nan=False,
    )
    add("frozen_target_reproduction", int((~target_match).sum()))
    return failures


def _construction_gates(
    metrics: pd.DataFrame,
    failures: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[str], str | None]:
    overall = metrics[metrics["scope"].eq("overall")].set_index("model_id")
    baseline = overall.loc[E0]
    gates = {}
    qualified = []
    for model_id in CANDIDATES:
        candidate = overall.loc[model_id]
        conditions = {
            "zero_invariant_failures": not failures,
            "positive_mean_trade_net_r": candidate["mean_trade_net_r"] > 0,
            "profit_factor_above_one": candidate["profit_factor"] > 1,
            "mean_opportunity_improvement_over_parent": (
                candidate["mean_opportunity_net_r"]
                > baseline["mean_opportunity_net_r"]
            ),
        }
        passed = all(conditions.values())
        gates[model_id] = {
            "conditions": {key: bool(value) for key, value in conditions.items()},
            "passed": passed,
        }
        if passed:
            qualified.append(model_id)
    winner = (
        max(
            qualified,
            key=lambda model_id: float(
                overall.loc[model_id, "mean_opportunity_net_r"]
            ),
        )
        if qualified
        else None
    )
    return gates, qualified, winner


def run_phase1_5_construction(
    project_root: Path,
    data_root: Path,
    *,
    artifact_root: Path | None = None,
) -> Phase15Result:
    """Open 2024 P&L only for the committed coverage-eligible variants."""

    config = load_project_config(project_root / "config")
    coverage_parent = (
        project_root
        / "artifacts"
        / "phase1_5"
        / "coverage"
        / config.phase1_5_coverage_selection.coverage_fingerprint
    )
    coverage_path = coverage_parent / "coverage-signals.parquet"
    phase14_parent = (
        project_root
        / "artifacts"
        / "phase1_4"
        / "construction"
        / config.phase1_5.parent.structural_construction_fingerprint
    )
    parent_paths = [
        phase14_parent / "structural-stop-mappings.parquet",
        phase14_parent / "trades-primary.parquet",
        phase14_parent / "trades-stress.parquet",
    ]
    phase11_parent = (
        project_root
        / "artifacts"
        / "phase1_1"
        / config.phase1_5.parent.signal_fingerprint
        / "opportunities.parquet"
    )
    required = [coverage_path, *parent_paths, phase11_parent]
    for path in required:
        if not path.is_file():
            raise ValueError(f"Phase 1.5 construction input is missing: {path}")

    year = config.phase1_5.scope.construction_year
    m1_paths = [
        m1_month_path(data_root, config.research.instrument.symbol, year, month)
        for month in range(1, 13)
    ]
    m5_paths = canonical_m5_paths(data_root, config.research)
    fingerprint, input_hashes = _fingerprint(
        project_root, [*m5_paths, *m1_paths, *required]
    )
    output_parent = (
        artifact_root or project_root / "artifacts" / "phase1_5" / "construction"
    )
    output = output_parent / fingerprint
    output.mkdir(parents=True, exist_ok=True)

    coverage = pd.read_parquet(coverage_path)
    eligible = {
        item.id for item in config.phase1_5_coverage_selection.eligible_candidates
    }
    coverage = coverage[coverage["model_id"].isin(eligible)].copy()
    mappings = pd.read_parquet(parent_paths[0])
    mappings = mappings[mappings["year"].eq(year)].copy()
    parent_primary = pd.read_parquet(parent_paths[1])
    parent_primary = parent_primary[
        parent_primary["model_id"].eq("p3_structure_target_2atr")
    ].copy()
    parent_stress = pd.read_parquet(parent_paths[2])
    parent_stress = parent_stress[
        parent_stress["model_id"].eq("p3_structure_target_2atr")
    ].copy()
    opportunities = pd.read_parquet(phase11_parent)
    opportunity_count = int(opportunities["year"].eq(year).sum())
    m5_all = load_canonical_m5(data_root, config.research)
    m5 = m5_all[m5_all["timestamp"].dt.year.eq(year)].reset_index(drop=True)
    m1 = load_m1_year(data_root, config, year)

    primary_candidates = simulate_delayed_entries(
        coverage,
        mappings,
        m5,
        m1,
        config,
        slippage_pips_per_side=(
            config.phase1_5.execution.primary_slippage_pips_per_side
        ),
    )
    stress_candidates = simulate_delayed_entries(
        coverage,
        mappings,
        m5,
        m1,
        config,
        slippage_pips_per_side=(
            config.phase1_5.execution.stress_slippage_pips_per_side
        ),
    )
    baseline = _baseline_e0(parent_primary)
    stress_baseline = _baseline_e0(parent_stress)
    primary = pd.concat([baseline, primary_candidates], ignore_index=True, sort=False)
    stress = pd.concat(
        [stress_baseline, stress_candidates], ignore_index=True, sort=False
    )
    metrics = _construction_metrics(primary, opportunity_count)
    stress_metrics = _construction_metrics(stress, opportunity_count)
    failures = _construction_invariant_failures(
        coverage, mappings, primary_candidates, baseline, config
    )
    gates, qualified, winner = _construction_gates(metrics, failures)
    summary = {
        "phase": config.phase1_5.phase,
        "stage": "construction_pnl",
        "fingerprint": fingerprint,
        "coverage_fingerprint": (
            config.phase1_5_coverage_selection.coverage_fingerprint
        ),
        "parent_fingerprint": (
            config.phase1_5.parent.structural_construction_fingerprint
        ),
        "eligible_candidates": sorted(eligible),
        "invariant_failure_count": sum(
            int(item["failure_count"]) for item in failures
        ),
        "invariant_failures": failures,
        "construction_gates": gates,
        "qualified_candidates": qualified,
        "recommended_winner": winner,
        "replication_permitted": winner is not None,
        "replication_returns_calculated": False,
    }

    primary.to_parquet(output / "trades-primary.parquet", index=False)
    stress.to_parquet(output / "trades-stress.parquet", index=False)
    metrics.to_csv(output / "metrics-primary.csv", index=False)
    stress_metrics.to_csv(output / "metrics-stress.csv", index=False)
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    manifest = {
        "phase": config.phase1_5.phase,
        "stage": "construction_pnl",
        "fingerprint": fingerprint,
        "coverage_fingerprint": (
            config.phase1_5_coverage_selection.coverage_fingerprint
        ),
        "created_at": datetime.now(UTC).isoformat(),
        "input_hashes": input_hashes,
        "artifact_files": sorted(path.name for path in output.iterdir()),
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return Phase15Result(artifact_directory=output, summary=summary)
