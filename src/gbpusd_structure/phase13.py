"""Phase-1.3 pathwise MAE/MFE and stop-adequacy diagnostics."""

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
from gbpusd_structure.phase0 import _fingerprint

SEQUENCE_LABELS = (
    "target_before_stop",
    "stop_then_target_later",
    "stop_without_later_target",
    "same_bar_ambiguous_stop_first",
    "neither_touched",
)
STOP_FIRST_LABELS = {
    "stop_then_target_later",
    "stop_without_later_target",
    "same_bar_ambiguous_stop_first",
}


@dataclass(frozen=True)
class Phase13Result:
    artifact_directory: Path
    summary: dict[str, Any]


def _first_touch(values: np.ndarray, threshold: float) -> int | None:
    positions = np.flatnonzero(values >= threshold)
    return int(positions[0]) if len(positions) else None


def _sequence_label(
    adverse_path_atr: np.ndarray,
    favorable_path_atr: np.ndarray,
    *,
    stop_atr: float,
    target_atr: float,
) -> tuple[str, int | None, int | None]:
    """Classify first threshold touches without guessing within-bar order."""

    stop_position = _first_touch(adverse_path_atr, stop_atr)
    target_position = _first_touch(favorable_path_atr, target_atr)
    if stop_position is None and target_position is None:
        label = "neither_touched"
    elif stop_position is None:
        label = "target_before_stop"
    elif target_position is None:
        label = "stop_without_later_target"
    elif target_position < stop_position:
        label = "target_before_stop"
    elif stop_position < target_position:
        label = "stop_then_target_later"
    else:
        label = "same_bar_ambiguous_stop_first"
    return label, stop_position, target_position


def _measure_signal_path(
    signal: dict[str, Any],
    m5: pd.DataFrame,
) -> tuple[dict[str, Any], np.ndarray, np.ndarray, pd.Series]:
    timestamps = pd.to_datetime(m5["timestamp"], utc=True)
    timestamp_values = timestamps.astype("int64").to_numpy()
    decision_at = pd.Timestamp(signal["decision_at"])
    cutoff_at = pd.Timestamp(signal["cutoff_at"])
    entry_position = int(
        np.searchsorted(timestamp_values, decision_at.value, side="left")
    )
    cutoff_position = int(
        np.searchsorted(timestamp_values, cutoff_at.value, side="left")
    )
    if entry_position >= len(m5) or entry_position >= cutoff_position:
        raise ValueError(f"No executable M5 path for {signal['signal_id']}")

    entry_bar = m5.iloc[entry_position]
    path = m5.iloc[entry_position:cutoff_position]
    path_timestamps = timestamps.iloc[entry_position:cutoff_position].reset_index(
        drop=True
    )
    entry_at = pd.Timestamp(entry_bar["timestamp"])
    atr = float(signal["atr"])
    if entry_at < decision_at or entry_at >= cutoff_at:
        raise ValueError(f"Invalid entry time for {signal['signal_id']}")
    if not np.isfinite(atr) or atr <= 0:
        raise ValueError(f"Invalid ATR for {signal['signal_id']}")

    if signal["direction"] == "long":
        reference_entry = float(entry_bar["ask_open"])
        adverse_path = (
            reference_entry - path["bid_low"].to_numpy(dtype="float64")
        ) / atr
        favorable_path = (
            path["bid_high"].to_numpy(dtype="float64") - reference_entry
        ) / atr
    elif signal["direction"] == "short":
        reference_entry = float(entry_bar["bid_open"])
        adverse_path = (
            path["ask_high"].to_numpy(dtype="float64") - reference_entry
        ) / atr
        favorable_path = (
            reference_entry - path["ask_low"].to_numpy(dtype="float64")
        ) / atr
    else:
        raise ValueError(f"Unknown direction for {signal['signal_id']}")

    adverse_path = np.maximum(adverse_path, 0.0)
    favorable_path = np.maximum(favorable_path, 0.0)
    record = {
        key: signal[key]
        for key in (
            "signal_id",
            "opportunity_id",
            "session",
            "session_date",
            "year",
            "period",
            "direction",
            "event_type",
            "decision_at",
            "cutoff_at",
            "atr",
        )
    }
    record.update(
        {
            "entry_at": entry_at,
            "entry_reference_price": reference_entry,
            "observed_m5_bar_count": len(path),
            "last_observed_bar_at": pd.Timestamp(path_timestamps.iloc[-1]),
            "max_adverse_excursion_atr": float(adverse_path.max()),
            "max_favorable_excursion_atr": float(favorable_path.max()),
        }
    )
    return record, adverse_path, favorable_path, path_timestamps


def _touch_at(timestamps: pd.Series, position: int | None) -> pd.Timestamp | None:
    return None if position is None else pd.Timestamp(timestamps.iloc[position])


def build_excursion_audit(
    signals: pd.DataFrame,
    m5: pd.DataFrame,
    config: ProjectConfig,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Measure full paths and preregistered stop/target threshold sequences."""

    excursion_rows: list[dict[str, Any]] = []
    threshold_rows: list[dict[str, Any]] = []
    stops = config.phase1_3.thresholds.stop_atr_multiples
    fixed_target = config.phase1_3.thresholds.fixed_target_atr
    rr_multiple = config.phase1_3.thresholds.rr_preserving_target_multiple

    for signal in signals.to_dict("records"):
        record, adverse, favorable, timestamps = _measure_signal_path(signal, m5)
        excursion_rows.append(record)
        for stop_atr in stops:
            targets = (
                ("fixed_2atr", fixed_target),
                ("rr_preserving_2_to_1", stop_atr * rr_multiple),
            )
            for target_mode, target_atr in targets:
                label, stop_position, target_position = _sequence_label(
                    adverse,
                    favorable,
                    stop_atr=stop_atr,
                    target_atr=target_atr,
                )
                threshold_rows.append(
                    {
                        **{
                            key: record[key]
                            for key in (
                                "signal_id",
                                "opportunity_id",
                                "session",
                                "session_date",
                                "year",
                                "period",
                                "direction",
                                "event_type",
                            )
                        },
                        "stop_atr": stop_atr,
                        "target_mode": target_mode,
                        "target_atr": target_atr,
                        "sequence": label,
                        "stop_touch_bar_at": _touch_at(timestamps, stop_position),
                        "target_touch_bar_at": _touch_at(
                            timestamps, target_position
                        ),
                    }
                )

    excursions = pd.DataFrame.from_records(excursion_rows)
    paths = pd.DataFrame.from_records(threshold_rows)
    original = paths[
        paths["stop_atr"].eq(1.0) & paths["target_mode"].eq("fixed_2atr")
    ][["signal_id", "sequence"]].rename(
        columns={"sequence": "original_fixed_sequence"}
    )
    paths = paths.merge(original, on="signal_id", how="left", validate="many_to_one")
    paths["saved_original_premature"] = (
        paths["target_mode"].eq("fixed_2atr")
        & paths["original_fixed_sequence"].eq("stop_then_target_later")
        & paths["sequence"].eq("target_before_stop")
    )
    return excursions, paths


def _scopes(frame: pd.DataFrame) -> list[tuple[str, str, pd.DataFrame]]:
    output = [("overall", "all", frame)]
    output.extend(
        ("session", value, frame[frame["session"].eq(value)])
        for value in ("london", "new_york")
    )
    output.extend(
        ("direction", value, frame[frame["direction"].eq(value)])
        for value in ("long", "short")
    )
    return output


def summarize_excursions(
    excursions: pd.DataFrame,
    config: ProjectConfig,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    quantiles = config.phase1_3.reporting.excursion_quantiles
    stops = config.phase1_3.thresholds.stop_atr_multiples
    for period in config.phase1_3.scope.periods:
        period_frame = excursions[excursions["period"].eq(period)]
        for scope, value, frame in _scopes(period_frame):
            row: dict[str, Any] = {
                "period": period,
                "scope": scope,
                "value": value,
                "signal_count": len(frame),
            }
            mae = frame["max_adverse_excursion_atr"]
            mfe = frame["max_favorable_excursion_atr"]
            for quantile in quantiles:
                suffix = f"q{round(quantile * 100):02d}"
                row[f"mae_atr_{suffix}"] = float(mae.quantile(quantile))
                row[f"mfe_atr_{suffix}"] = float(mfe.quantile(quantile))
            for stop in stops:
                suffix = str(stop).replace(".", "_")
                row[f"mae_ge_{suffix}_atr_rate"] = float(mae.ge(stop).mean())
            for target in (1.0, 2.0, 3.0):
                suffix = str(target).replace(".", "_")
                row[f"mfe_ge_{suffix}_atr_rate"] = float(mfe.ge(target).mean())
            rows.append(row)
    return pd.DataFrame.from_records(rows)


def summarize_threshold_paths(
    paths: pd.DataFrame,
    config: ProjectConfig,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for period in config.phase1_3.scope.periods:
        period_frame = paths[paths["period"].eq(period)]
        for scope, value, scoped in _scopes(period_frame):
            for (stop_atr, target_mode), frame in scoped.groupby(
                ["stop_atr", "target_mode"], sort=True
            ):
                counts = frame["sequence"].value_counts()
                stop_first_count = int(
                    frame["sequence"].isin(STOP_FIRST_LABELS).sum()
                )
                strict_count = int(
                    counts.get("stop_then_target_later", 0)
                )
                row = {
                    "period": period,
                    "scope": scope,
                    "value": value,
                    "stop_atr": float(stop_atr),
                    "target_mode": target_mode,
                    "target_atr": float(frame["target_atr"].iloc[0]),
                    "signal_count": len(frame),
                    "stop_first_count": stop_first_count,
                    "strict_premature_stop_count": strict_count,
                    "strict_premature_stop_rate": (
                        strict_count / stop_first_count
                        if stop_first_count
                        else None
                    ),
                    "saved_original_premature_count": int(
                        frame["saved_original_premature"].sum()
                    ),
                }
                for label in SEQUENCE_LABELS:
                    row[f"{label}_count"] = int(counts.get(label, 0))
                    row[f"{label}_rate"] = float(frame["sequence"].eq(label).mean())
                rows.append(row)
    return pd.DataFrame.from_records(rows)


def _invariant_failures(
    excursions: pd.DataFrame,
    paths: pd.DataFrame,
    parent_trades: pd.DataFrame,
    config: ProjectConfig,
) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []

    def add(name: str, count: int) -> None:
        if count:
            failures.append({"invariant": name, "failure_count": int(count)})

    add("one_excursion_per_parent_trade", abs(len(excursions) - len(parent_trades)))
    add("duplicate_excursion_signal", int(excursions["signal_id"].duplicated().sum()))
    add(
        "non_positive_atr",
        int((~np.isfinite(excursions["atr"]) | excursions["atr"].le(0)).sum()),
    )
    add(
        "negative_excursion",
        int(
            (
                excursions["max_adverse_excursion_atr"].lt(0)
                | excursions["max_favorable_excursion_atr"].lt(0)
            ).sum()
        ),
    )
    add(
        "entry_before_decision",
        int(excursions["entry_at"].lt(excursions["decision_at"]).sum()),
    )
    add(
        "path_reaches_cutoff",
        int(excursions["last_observed_bar_at"].ge(excursions["cutoff_at"]).sum()),
    )

    expected_paths = (
        len(excursions)
        * len(config.phase1_3.thresholds.stop_atr_multiples)
        * 2
    )
    add("threshold_path_count", abs(len(paths) - expected_paths))
    add("unknown_sequence", int((~paths["sequence"].isin(SEQUENCE_LABELS)).sum()))

    original = paths[
        paths["stop_atr"].eq(1.0) & paths["target_mode"].eq("fixed_2atr")
    ][["signal_id", "sequence"]]
    comparison = parent_trades[
        ["signal_id", "entry_at", "entry_reference_price", "exit_reason"]
    ].merge(
        excursions[["signal_id", "entry_at", "entry_reference_price"]],
        on="signal_id",
        suffixes=("_parent", "_audit"),
        how="outer",
        indicator=True,
    ).merge(original, on="signal_id", how="left")
    add("parent_signal_membership", int(comparison["_merge"].ne("both").sum()))
    add(
        "entry_timestamp_reproduction",
        int(comparison["entry_at_parent"].ne(comparison["entry_at_audit"]).sum()),
    )
    price_match = np.isclose(
        comparison["entry_reference_price_parent"],
        comparison["entry_reference_price_audit"],
        rtol=0,
        atol=1e-12,
        equal_nan=False,
    )
    add("entry_price_reproduction", int((~price_match).sum()))

    parent_stop = comparison["exit_reason"].astype(str).str.startswith("stop")
    audit_stop = comparison["sequence"].isin(STOP_FIRST_LABELS)
    parent_target = comparison["exit_reason"].astype(str).str.startswith("target")
    audit_target = comparison["sequence"].eq("target_before_stop")
    add("original_stop_touch_reproduction", int(parent_stop.ne(audit_stop).sum()))
    add(
        "original_target_touch_reproduction",
        int(parent_target.ne(audit_target).sum()),
    )
    return failures


def _json_default(value: Any) -> Any:
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    raise TypeError(f"Cannot serialize {type(value).__name__}")


def run_phase1_3(
    project_root: Path,
    data_root: Path,
    *,
    artifact_root: Path | None = None,
) -> Phase13Result:
    """Run the frozen P3 full-session path audit without strategy selection."""

    config = load_project_config(project_root / "config")
    parent = (
        project_root
        / "artifacts"
        / "phase1_1"
        / config.phase1_3.parent.fingerprint
    )
    signal_path = parent / "signals.parquet"
    trade_path = parent / "trades-primary.parquet"
    for path in (signal_path, trade_path):
        if not path.is_file():
            raise ValueError(f"Phase 1.3 parent artifact is missing: {path}")

    raw_paths = canonical_m5_paths(data_root, config.research)
    fingerprint, input_hashes = _fingerprint(
        project_root, [*raw_paths, signal_path, trade_path]
    )
    output_parent = artifact_root or project_root / "artifacts" / "phase1_3"
    output = output_parent / fingerprint
    output.mkdir(parents=True, exist_ok=True)

    model = config.phase1_3.parent.baseline_model
    parent_signals = pd.read_parquet(signal_path)
    signals = parent_signals[parent_signals["model_id"].eq(model)].copy()
    signals = signals.sort_values(["decision_at", "signal_id"], kind="stable")
    parent_trades = pd.read_parquet(trade_path)
    parent_trades = parent_trades[parent_trades["model_id"].eq(model)].copy()
    m5 = load_canonical_m5(data_root, config.research)

    excursions, paths = build_excursion_audit(signals, m5, config)
    excursion_summary = summarize_excursions(excursions, config)
    threshold_summary = summarize_threshold_paths(paths, config)
    failures = _invariant_failures(
        excursions, paths, parent_trades, config
    )

    headline_rows = threshold_summary[
        threshold_summary["scope"].eq("overall")
        & threshold_summary["stop_atr"].eq(1.0)
        & threshold_summary["target_mode"].eq("fixed_2atr")
    ]
    summary = {
        "phase": config.phase1_3.phase,
        "fingerprint": fingerprint,
        "parent_fingerprint": config.phase1_3.parent.fingerprint,
        "baseline_model": model,
        "diagnostic_only": True,
        "strategy_pnl_selection": False,
        "signal_count": len(excursions),
        "signal_counts_by_period": {
            period: int(excursions["period"].eq(period).sum())
            for period in config.phase1_3.scope.periods
        },
        "original_1atr_2atr_path": {
            row["period"]: {
                "signal_count": int(row["signal_count"]),
                "stop_first_count": int(row["stop_first_count"]),
                "strict_premature_stop_count": int(
                    row["strict_premature_stop_count"]
                ),
                "strict_premature_stop_rate": row[
                    "strict_premature_stop_rate"
                ],
                "same_bar_ambiguous_count": int(
                    row["same_bar_ambiguous_stop_first_count"]
                ),
                "stop_without_later_target_count": int(
                    row["stop_without_later_target_count"]
                ),
                "target_before_stop_count": int(
                    row["target_before_stop_count"]
                ),
                "neither_touched_count": int(row["neither_touched_count"]),
            }
            for row in headline_rows.to_dict("records")
        },
        "invariant_failure_count": sum(
            int(item["failure_count"]) for item in failures
        ),
        "invariant_failures": failures,
    }

    excursions.to_parquet(output / "excursions.parquet", index=False)
    paths.to_parquet(output / "threshold-paths.parquet", index=False)
    excursion_summary.to_csv(output / "excursion-summary.csv", index=False)
    threshold_summary.to_csv(output / "threshold-summary.csv", index=False)
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True, default=_json_default) + "\n",
        encoding="utf-8",
    )
    manifest = {
        "phase": config.phase1_3.phase,
        "fingerprint": fingerprint,
        "parent_fingerprint": config.phase1_3.parent.fingerprint,
        "created_at": datetime.now(UTC).isoformat(),
        "input_hashes": input_hashes,
        "config_status": config.phase1_3.status,
        "artifact_files": sorted(path.name for path in output.iterdir()),
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return Phase13Result(artifact_directory=output, summary=summary)

