"""Phase-0 definition audit: causal labels, stability, and reporting only."""

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
from gbpusd_structure.data import canonical_m5_paths, load_canonical_m5
from gbpusd_structure.structure import (
    add_atr,
    build_support_resistance_zones,
    eligible_structure_bars,
    label_fair_value_gaps,
    label_structure_breaks,
    label_swings,
)
from gbpusd_structure.timeframes import build_timeframes

TIMEFRAME_ORDER = ("15min", "1H", "4H", "1D")


@dataclass(frozen=True)
class Phase0Result:
    artifact_directory: Path
    summary: dict[str, Any]


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    return frame.replace({np.nan: None}).to_dict("records")


def _describe(values: pd.Series) -> dict[str, float | int | None]:
    clean = pd.to_numeric(values, errors="coerce").dropna()
    if clean.empty:
        return {"count": 0, "median": None, "p05": None, "p95": None}
    return {
        "count": len(clean),
        "median": float(clean.median()),
        "p05": float(clean.quantile(0.05)),
        "p95": float(clean.quantile(0.95)),
    }


def _event_keys(frame: pd.DataFrame, columns: list[str]) -> set[tuple[Any, ...]]:
    if frame.empty:
        return set()
    return set(frame[columns].itertuples(index=False, name=None))


def _jaccard(primary: set[tuple[Any, ...]], comparison: set[tuple[Any, ...]]) -> float:
    union = primary | comparison
    return len(primary & comparison) / len(union) if union else 1.0


def _fingerprint(
    project_root: Path,
    input_paths: list[Path],
) -> tuple[str, dict[str, str]]:
    digest = hashlib.sha256()
    input_hashes: dict[str, str] = {}
    for path in sorted((project_root / "config").glob("*.yaml")):
        content = path.read_bytes()
        digest.update(path.name.encode())
        digest.update(content)
    for path in sorted((project_root / "src").rglob("*.py")):
        content = path.read_bytes()
        digest.update(str(path.relative_to(project_root)).encode())
        digest.update(content)
    for path in input_paths:
        file_digest = hashlib.sha256()
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                file_digest.update(chunk)
        value = file_digest.hexdigest()
        input_hashes[path.name] = value
        digest.update(path.name.encode())
        digest.update(value.encode())
    return digest.hexdigest()[:16], input_hashes


def _prepare_bars(
    m5: pd.DataFrame,
    config: ProjectConfig,
) -> dict[str, pd.DataFrame]:
    output: dict[str, pd.DataFrame] = {}
    for timeframe, bars in build_timeframes(m5).items():
        enriched = add_atr(bars, config.structure.volatility.atr_period)
        output[timeframe] = eligible_structure_bars(
            enriched,
            config.structure.audit.minimum_bar_coverage_ratio,
        )
    return output


def _primary_labels(
    bars_by_timeframe: dict[str, pd.DataFrame],
    config: ProjectConfig,
) -> tuple[
    dict[str, pd.DataFrame],
    dict[str, pd.DataFrame],
    dict[str, pd.DataFrame],
    dict[str, pd.DataFrame],
    dict[str, pd.DataFrame],
]:
    swings: dict[str, pd.DataFrame] = {}
    breaks: dict[str, pd.DataFrame] = {}
    gaps: dict[str, pd.DataFrame] = {}
    zones: dict[str, pd.DataFrame] = {}
    snapshots: dict[str, pd.DataFrame] = {}
    for timeframe in TIMEFRAME_ORDER:
        bars = bars_by_timeframe[timeframe]
        swing = label_swings(
            bars,
            config.structure,
            pip_size=config.research.instrument.pip_size,
        )
        swings[timeframe] = swing
        breaks[timeframe] = label_structure_breaks(
            bars,
            swing,
            config.structure,
            pip_size=config.research.instrument.pip_size,
        )
        gaps[timeframe] = label_fair_value_gaps(bars, config.structure)
        if timeframe in config.structure.support_resistance.source_timeframes:
            zones[timeframe], snapshots[timeframe] = (
                build_support_resistance_zones(
                    swing,
                    bars,
                    config.structure,
                )
            )
    return swings, breaks, gaps, zones, snapshots


def _sensitivity_audit(
    bars_by_timeframe: dict[str, pd.DataFrame],
    primary_swings: dict[str, pd.DataFrame],
    primary_breaks: dict[str, pd.DataFrame],
    primary_gaps: dict[str, pd.DataFrame],
    primary_snapshots: dict[str, pd.DataFrame],
    config: ProjectConfig,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    structure = config.structure
    pip_size = config.research.instrument.pip_size

    for timeframe in TIMEFRAME_ORDER:
        bars = bars_by_timeframe[timeframe]
        swing_primary_keys = _event_keys(
            primary_swings[timeframe], ["event_at", "direction"]
        )
        swing_variants: dict[int, pd.DataFrame] = {
            structure.swings.right_bars: primary_swings[timeframe]
        }
        for right_bars in (1, 2, 3):
            variant = swing_variants.get(right_bars)
            if variant is None:
                variant = label_swings(
                    bars,
                    structure,
                    pip_size=pip_size,
                    right_bars=right_bars,
                )
                swing_variants[right_bars] = variant
            if right_bars != structure.swings.right_bars:
                keys = _event_keys(variant, ["event_at", "direction"])
                rows.append(
                    {
                        "concept": "swing",
                        "timeframe": timeframe,
                        "parameter": "right_bars",
                        "primary_value": structure.swings.right_bars,
                        "comparison_value": right_bars,
                        "primary_count": len(swing_primary_keys),
                        "comparison_count": len(keys),
                        "intersection_count": len(swing_primary_keys & keys),
                        "jaccard_agreement": _jaccard(swing_primary_keys, keys),
                    }
                )

        break_primary_keys = _event_keys(
            primary_breaks[timeframe],
            ["event_at", "direction", "event_type"],
        )
        for buffer_ratio in (0.0, 0.05, 0.10):
            if np.isclose(buffer_ratio, structure.breaks.minimum_buffer_atr):
                continue
            variant = label_structure_breaks(
                bars,
                primary_swings[timeframe],
                structure,
                pip_size=pip_size,
                break_buffer_atr=buffer_ratio,
            )
            keys = _event_keys(
                variant, ["event_at", "direction", "event_type"]
            )
            rows.append(
                {
                    "concept": "structure_break",
                    "timeframe": timeframe,
                    "parameter": "buffer_atr",
                    "primary_value": structure.breaks.minimum_buffer_atr,
                    "comparison_value": buffer_ratio,
                    "primary_count": len(break_primary_keys),
                    "comparison_count": len(keys),
                    "intersection_count": len(break_primary_keys & keys),
                    "jaccard_agreement": _jaccard(break_primary_keys, keys),
                }
            )

        gap_primary_keys = _event_keys(
            primary_gaps[timeframe], ["event_at", "direction"]
        )
        for minimum_ratio in (0.0, 0.10, 0.20):
            if np.isclose(
                minimum_ratio, structure.fair_value_gap.minimum_size_atr
            ):
                continue
            variant = label_fair_value_gaps(
                bars,
                structure,
                minimum_size_atr=minimum_ratio,
            )
            keys = _event_keys(variant, ["event_at", "direction"])
            rows.append(
                {
                    "concept": "fair_value_gap",
                    "timeframe": timeframe,
                    "parameter": "minimum_size_atr",
                    "primary_value": structure.fair_value_gap.minimum_size_atr,
                    "comparison_value": minimum_ratio,
                    "primary_count": len(gap_primary_keys),
                    "comparison_count": len(keys),
                    "intersection_count": len(gap_primary_keys & keys),
                    "jaccard_agreement": _jaccard(gap_primary_keys, keys),
                }
            )

        if timeframe in structure.support_resistance.source_timeframes:
            primary = primary_snapshots[timeframe]
            primary_active = primary[primary["active"]]
            primary_keys = _event_keys(primary_active, ["swing_id"])
            for tolerance in (0.10, 0.20, 0.30):
                if np.isclose(
                    tolerance,
                    structure.support_resistance.cluster_tolerance_atr,
                ):
                    continue
                _, variant = build_support_resistance_zones(
                    primary_swings[timeframe],
                    bars,
                    structure,
                    cluster_tolerance_atr=tolerance,
                )
                variant_active = variant[variant["active"]]
                keys = _event_keys(variant_active, ["swing_id"])
                rows.append(
                    {
                        "concept": "support_resistance",
                        "timeframe": timeframe,
                        "parameter": "cluster_tolerance_atr",
                        "primary_value": (
                            structure.support_resistance.cluster_tolerance_atr
                        ),
                        "comparison_value": tolerance,
                        "primary_count": len(primary_keys),
                        "comparison_count": len(keys),
                        "intersection_count": len(primary_keys & keys),
                        "jaccard_agreement": _jaccard(primary_keys, keys),
                    }
                )
    return pd.DataFrame.from_records(rows)


def _annual_and_monthly_counts(
    collections: dict[str, dict[str, pd.DataFrame]],
    years: tuple[int, ...],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    annual: list[dict[str, Any]] = []
    monthly: list[dict[str, Any]] = []
    for concept, by_timeframe in collections.items():
        for timeframe, frame in by_timeframe.items():
            if frame.empty:
                continue
            timestamp_column = "active_at" if concept == "active_zone" else "event_at"
            available = frame[pd.notna(frame[timestamp_column])].copy()
            if concept == "active_zone":
                available = available[available["touch_count"].ge(2)]
            available["year"] = available[timestamp_column].dt.year
            available["month"] = available[timestamp_column].dt.strftime("%Y-%m")
            yearly_counts = available.groupby("year", observed=True).size()
            for year in years:
                annual.append(
                    {
                        "concept": concept,
                        "timeframe": timeframe,
                        "year": int(year),
                        "count": int(yearly_counts.get(year, 0)),
                    }
                )
            for month, group in available.groupby("month", observed=True):
                monthly.append(
                    {
                        "concept": concept,
                        "timeframe": timeframe,
                        "month": month,
                        "count": len(group),
                    }
                )
    return pd.DataFrame(annual), pd.DataFrame(monthly)


def _point_in_time_failures(
    bars_by_timeframe: dict[str, pd.DataFrame],
    collections: dict[str, dict[str, pd.DataFrame]],
) -> list[str]:
    failures: list[str] = []
    for timeframe, bars in bars_by_timeframe.items():
        if bars["bar_id"].duplicated().any():
            failures.append(f"{timeframe}: duplicate bar_id")
        if not bars["available_at"].gt(bars["timestamp"]).all():
            failures.append(f"{timeframe}: non-causal bar availability")
        invalid_ohlc = (
            bars["mid_high"].lt(bars[["mid_open", "mid_close"]].max(axis=1))
            | bars["mid_low"].gt(bars[["mid_open", "mid_close"]].min(axis=1))
            | bars["mid_high"].lt(bars["mid_low"])
        )
        if invalid_ohlc.any():
            failures.append(f"{timeframe}: invalid aggregated OHLC")

    for concept, by_timeframe in collections.items():
        for timeframe, frame in by_timeframe.items():
            if frame.empty:
                continue
            if "event_id" in frame and frame["event_id"].duplicated().any():
                failures.append(f"{concept}/{timeframe}: duplicate event_id")
            if {"event_at", "available_at"}.issubset(
                frame.columns
            ) and not frame["available_at"].gt(frame["event_at"]).all():
                failures.append(
                    f"{concept}/{timeframe}: non-causal event availability"
                )
            if concept == "swing":
                invalid_confirmation = (
                    frame["confirmation_index"] - frame["pivot_index"]
                    != frame["confirmation_delay_bars"]
                )
                if invalid_confirmation.any():
                    failures.append(
                        f"{concept}/{timeframe}: invalid confirmation delay"
                    )
            if concept == "fair_value_gap":
                for column in ("partial_fill_at", "full_fill_at"):
                    observed = frame[pd.notna(frame[column])]
                    if not observed[column].gt(observed["available_at"]).all():
                        failures.append(
                            f"{concept}/{timeframe}: invalid {column} lifecycle"
                        )
    return failures


def _transition_counts(events: pd.DataFrame) -> dict[str, int]:
    classified = events[events["event_type"].isin(["bos", "choch"])].copy()
    if len(classified) < 2:
        return {}
    labels = classified["event_type"] + ":" + classified["direction"]
    transitions = labels.shift(1) + " -> " + labels
    return {
        str(key): int(value)
        for key, value in transitions.dropna().value_counts().items()
    }


def _build_summary(
    bars_by_timeframe: dict[str, pd.DataFrame],
    swings: dict[str, pd.DataFrame],
    breaks: dict[str, pd.DataFrame],
    gaps: dict[str, pd.DataFrame],
    zones: dict[str, pd.DataFrame],
    snapshots: dict[str, pd.DataFrame],
    annual: pd.DataFrame,
    sensitivity: pd.DataFrame,
    failures: list[str],
    config: ProjectConfig,
) -> dict[str, Any]:
    timeframe_rows: list[dict[str, Any]] = []
    for timeframe in TIMEFRAME_ORDER:
        bars = bars_by_timeframe[timeframe]
        swing = swings[timeframe]
        break_events = breaks[timeframe]
        gap = gaps[timeframe]
        ambiguous_fraction = (
            float(swing["ambiguous_equal"].mean()) if len(swing) else None
        )
        combined = pd.concat(
            [
                swing[["available_at"]].assign(concept="swing"),
                break_events[["available_at"]].assign(concept="structure_break"),
                gap[["available_at"]].assign(concept="fair_value_gap"),
            ],
            ignore_index=True,
        )
        overlaps = int(
            combined.groupby("available_at", observed=True).size().gt(1).sum()
        )
        timeframe_rows.append(
            {
                "timeframe": timeframe,
                "bar_count": len(bars),
                "upstream_coverage_fraction": float(
                    bars["coverage_ratio"]
                    .ge(config.structure.audit.minimum_bar_coverage_ratio)
                    .mean()
                ),
                "structure_eligible_count": int(bars["structure_eligible"].sum()),
                "swing_count": len(swing),
                "ambiguous_swing_count": int(swing["ambiguous_equal"].sum()),
                "ambiguous_swing_fraction": ambiguous_fraction,
                "confirmation_delay_bars": _describe(
                    swing["confirmation_delay_bars"]
                ),
                "break_counts": {
                    str(key): int(value)
                    for key, value in break_events["event_type"]
                    .value_counts()
                    .items()
                },
                "displacement_qualified_break_fraction": (
                    float(break_events["displacement_qualified"].mean())
                    if len(break_events)
                    else None
                ),
                "break_transition_counts": _transition_counts(break_events),
                "fvg_count": len(gap),
                "fvg_status_counts": {
                    str(key): int(value)
                    for key, value in gap["status"].value_counts().items()
                },
                "fvg_size_atr": _describe(gap["size_atr"]),
                "fvg_fill_delay_bars": _describe(gap["fill_delay_bars"]),
                "overlapping_label_timestamp_count": overlaps,
            }
        )

    zone_rows: list[dict[str, Any]] = []
    for timeframe, frame in zones.items():
        active = frame[pd.notna(frame["active_at"])]
        zone_rows.append(
            {
                "timeframe": timeframe,
                "zone_count": len(frame),
                "active_zone_count": len(active),
                "width_pips": _describe(
                    (frame["upper_bound"] - frame["lower_bound"])
                    / config.research.instrument.pip_size
                ),
                "touch_count": _describe(frame["touch_count"]),
                "age_bars_at_sample_end": _describe(
                    frame["age_bars_at_sample_end"]
                ),
                "bars_since_last_touch": _describe(
                    frame["bars_since_last_touch"]
                ),
                "merged_touch_count": int((frame["touch_count"] - 1).sum()),
                "split_count": 0,
                "active_snapshot_count": int(snapshots[timeframe]["active"].sum()),
            }
        )

    gates: list[dict[str, Any]] = []
    audit = config.structure.audit
    for row in timeframe_rows:
        coverage = row["upstream_coverage_fraction"]
        gates.append(
            {
                "gate": "upstream_coverage",
                "scope": row["timeframe"],
                "value": coverage,
                "threshold": audit.minimum_bar_coverage_ratio,
                "passed": coverage >= audit.minimum_bar_coverage_ratio,
            }
        )
        ambiguity = row["ambiguous_swing_fraction"]
        gates.append(
            {
                "gate": "ambiguous_swing_fraction",
                "scope": row["timeframe"],
                "value": ambiguity,
                "threshold": audit.maximum_ambiguous_swing_fraction,
                "passed": bool(
                    ambiguity is not None
                    and ambiguity <= audit.maximum_ambiguous_swing_fraction
                ),
            }
        )
    for row in _records(annual):
        gates.append(
            {
                "gate": "annual_event_count",
                "scope": (
                    f"{row['concept']}/{row['timeframe']}/{row['year']}"
                ),
                "value": row["count"],
                "threshold": audit.minimum_events_per_year,
                "passed": row["count"] >= audit.minimum_events_per_year,
            }
        )
    for row in _records(sensitivity):
        gates.append(
            {
                "gate": "sensitivity_event_agreement",
                "scope": (
                    f"{row['concept']}/{row['timeframe']}/"
                    f"{row['parameter']}={row['comparison_value']}"
                ),
                "value": row["jaccard_agreement"],
                "threshold": audit.minimum_sensitivity_event_agreement,
                "passed": (
                    row["jaccard_agreement"]
                    >= audit.minimum_sensitivity_event_agreement
                ),
            }
        )
    gates.append(
        {
            "gate": "point_in_time_invariants",
            "scope": "all",
            "value": len(failures),
            "threshold": 0,
            "passed": not failures,
        }
    )
    failed = [gate for gate in gates if not gate["passed"]]
    return {
        "phase": 0,
        "purpose": "definition_audit_without_trading_or_pnl",
        "status": "pass" if not failed else "fail",
        "timeframes": timeframe_rows,
        "support_resistance": zone_rows,
        "annual_counts": _records(annual),
        "sensitivity": _records(sensitivity),
        "point_in_time_failures": failures,
        "gate": {
            "passed": not failed,
            "failed_count": len(failed),
            "checks": gates,
        },
    }


def _concat(by_timeframe: dict[str, pd.DataFrame]) -> pd.DataFrame:
    frames = [frame for frame in by_timeframe.values() if not frame.empty]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def run_phase0(
    project_root: Path,
    data_root: Path,
    *,
    artifact_root: Path | None = None,
) -> Phase0Result:
    """Run the registered Phase-0 audit and persist reproducible artifacts."""

    config = load_project_config(project_root / "config")
    input_paths = canonical_m5_paths(data_root, config.research)
    fingerprint, input_hashes = _fingerprint(project_root, input_paths)
    artifact_directory = (artifact_root or project_root / "artifacts" / "phase0")
    artifact_directory = artifact_directory / fingerprint
    artifact_directory.mkdir(parents=True, exist_ok=True)

    m5 = load_canonical_m5(data_root, config.research)
    bars_by_timeframe = _prepare_bars(m5, config)
    swings, breaks, gaps, zones, snapshots = _primary_labels(
        bars_by_timeframe, config
    )
    sensitivity = _sensitivity_audit(
        bars_by_timeframe,
        swings,
        breaks,
        gaps,
        snapshots,
        config,
    )
    collections = {
        "swing": swings,
        "structure_break": breaks,
        "fair_value_gap": gaps,
        "active_zone": zones,
    }
    years = tuple(
        range(
            config.research.periods.research_start.year,
            config.research.periods.research_end.year,
        )
    )
    annual, monthly = _annual_and_monthly_counts(collections, years)
    point_in_time_collections = {
        "swing": swings,
        "structure_break": breaks,
        "fair_value_gap": gaps,
        "zone_snapshot": snapshots,
    }
    failures = _point_in_time_failures(
        bars_by_timeframe, point_in_time_collections
    )
    summary = _build_summary(
        bars_by_timeframe,
        swings,
        breaks,
        gaps,
        zones,
        snapshots,
        annual,
        sensitivity,
        failures,
        config,
    )

    for timeframe, bars in bars_by_timeframe.items():
        bars.to_parquet(
            artifact_directory / f"bars-{timeframe}.parquet",
            index=False,
            compression="zstd",
        )
    tables = {
        "swings": _concat(swings),
        "structure-events": _concat(breaks),
        "fair-value-gaps": _concat(gaps),
        "support-resistance-zones": _concat(zones),
        "support-resistance-snapshots": _concat(snapshots),
    }
    for name, frame in tables.items():
        frame.to_parquet(
            artifact_directory / f"{name}.parquet",
            index=False,
            compression="zstd",
        )
    annual.to_csv(artifact_directory / "annual-counts.csv", index=False)
    monthly.to_csv(artifact_directory / "monthly-counts.csv", index=False)
    sensitivity.to_csv(artifact_directory / "sensitivity.csv", index=False)
    _write_json(artifact_directory / "summary.json", summary)

    artifact_hashes: dict[str, str] = {}
    for path in sorted(artifact_directory.iterdir()):
        if path.name == "manifest.json" or not path.is_file():
            continue
        artifact_hashes[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest = {
        "phase": 0,
        "fingerprint": fingerprint,
        "generated_at": datetime.now(UTC).isoformat(),
        "research_start": config.research.periods.research_start.isoformat(),
        "research_end_exclusive": config.research.periods.research_end.isoformat(),
        "price_source": config.research.data.price_source,
        "source_role": config.research.data.source_role,
        "input_sha256": input_hashes,
        "artifact_sha256": artifact_hashes,
        "contains_trades_or_pnl": False,
    }
    _write_json(artifact_directory / "manifest.json", manifest)
    return Phase0Result(artifact_directory=artifact_directory, summary=summary)
