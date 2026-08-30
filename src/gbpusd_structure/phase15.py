"""Phase-1.5 coverage-only FVG pullback entry funnel."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

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
