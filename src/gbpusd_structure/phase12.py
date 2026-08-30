"""Phase-1.2 staged light-filter study for the full-session P3 baseline."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from gbpusd_structure.config import ProjectConfig, load_project_config
from gbpusd_structure.data import canonical_m5_paths, load_canonical_m5
from gbpusd_structure.phase0 import _fingerprint
from gbpusd_structure.phase1 import _profit_factor, _simulate_signals

SAFE_CANDIDATE_COLUMNS = (
    "opportunity_id",
    "session",
    "session_date",
    "year",
    "period",
    "session_open_at",
    "observation_end_at",
    "cutoff_at",
    "decision_at",
    "direction",
    "event_type",
    "signal_bar_id",
    "setup_bar_at",
    "feature_available_at",
    "displacement_qualified",
    "source_event_id",
    "h1_context",
    "h4_context",
    "daily_context",
)
FORBIDDEN_COVERAGE_COLUMN_PARTS = (
    "return",
    "net_r",
    "net_pips",
    "pnl",
    "profit",
    "win",
    "entry_fill",
    "exit",
    "commission",
    "slippage",
)


@dataclass(frozen=True)
class Phase12StageResult:
    artifact_directory: Path
    summary: dict[str, Any]


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _stage_fingerprint(
    project_root: Path,
    parent_path: Path,
    stage: str,
) -> tuple[str, dict[str, str]]:
    inputs = {
        "phase1_2.yaml": _file_hash(project_root / "config" / "phase1_2.yaml"),
        "phase12.py": _file_hash(
            project_root / "src" / "gbpusd_structure" / "phase12.py"
        ),
        parent_path.name: _file_hash(parent_path),
    }
    digest = hashlib.sha256(stage.encode())
    for name, value in sorted(inputs.items()):
        digest.update(name.encode())
        digest.update(value.encode())
    return digest.hexdigest()[:16], inputs


def _opposition_mask(frame: pd.DataFrame, context_column: str) -> pd.Series:
    return (
        frame["direction"].eq("long") & frame[context_column].eq("bearish")
    ) | (
        frame["direction"].eq("short") & frame[context_column].eq("bullish")
    )


def filter_candidate_mask(
    frame: pd.DataFrame,
    rules: tuple[str, ...],
) -> pd.Series:
    """Return the frozen Phase-1.2 eligibility mask for one filter."""

    mask = pd.Series(True, index=frame.index)
    for rule in rules:
        if rule == "displacement":
            mask &= frame["displacement_qualified"].astype(bool)
        elif rule == "h1_opposition_veto":
            mask &= ~_opposition_mask(frame, "h1_context")
        elif rule == "h4_opposition_veto":
            mask &= ~_opposition_mask(frame, "h4_context")
        else:
            raise ValueError(f"Unknown Phase 1.2 filter rule: {rule}")
    return mask


def select_first_filter_candidates(
    candidates: pd.DataFrame,
    filter_id: str,
    rules: tuple[str, ...],
) -> pd.DataFrame:
    """Select the first candidate satisfying one filter in every session."""

    eligible = candidates[filter_candidate_mask(candidates, rules)].copy()
    selected = (
        eligible.sort_values(
            ["decision_at", "source_event_id"], kind="stable"
        )
        .groupby("opportunity_id", sort=False, as_index=False)
        .head(1)
        .copy()
    )
    selected.insert(0, "filter_id", filter_id)
    return selected.reset_index(drop=True)


def _coverage_invariant_failures(
    selected: pd.DataFrame,
    parent_candidates: pd.DataFrame,
    config: ProjectConfig,
) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []

    def add(name: str, count: int) -> None:
        if count:
            failures.append({"invariant": name, "failure_count": int(count)})

    add(
        "construction_rows_only",
        int(selected["year"].ne(config.phase1_2.scope.construction_year).sum()),
    )
    add(
        "one_signal_per_filter_session",
        int(selected.duplicated(["filter_id", "opportunity_id"]).sum()),
    )
    add(
        "feature_available_by_decision",
        int(selected["feature_available_at"].gt(selected["decision_at"]).sum()),
    )
    parent_keys = set(
        parent_candidates[
            ["opportunity_id", "source_event_id"]
        ].itertuples(index=False, name=None)
    )
    selected_keys = set(
        selected[["opportunity_id", "source_event_id"]].itertuples(
            index=False, name=None
        )
    )
    add("selected_from_parent_candidates", len(selected_keys - parent_keys))
    forbidden = [
        column
        for column in selected.columns
        if any(part in column.lower() for part in FORBIDDEN_COVERAGE_COLUMN_PARTS)
    ]
    if forbidden:
        failures.append(
            {"invariant": "coverage_contains_forbidden_columns", "columns": forbidden}
        )
    return failures


def _coverage_tables(
    selected: pd.DataFrame,
    config: ProjectConfig,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    records = []
    monthly_records = []
    months = pd.period_range(
        f"{config.phase1_2.scope.construction_year}-01",
        f"{config.phase1_2.scope.construction_year}-12",
        freq="M",
    ).astype(str)
    for candidate in config.phase1_2.coverage_screen.candidates:
        frame = selected[selected["filter_id"].eq(candidate.id)]
        count = len(frame)
        minimum = config.phase1_2.coverage_screen.target_trades_per_year_minimum
        maximum = config.phase1_2.coverage_screen.target_trades_per_year_maximum
        records.append(
            {
                "filter_id": candidate.id,
                "scope": "overall",
                "value": "all",
                "trade_count": count,
                "mean_trades_per_month": count / 12,
                "coverage_eligible": minimum <= count <= maximum,
            }
        )
        for column, scope in (("session", "session"), ("direction", "direction")):
            for value in sorted(frame[column].unique()):
                scoped = frame[frame[column].eq(value)]
                records.append(
                    {
                        "filter_id": candidate.id,
                        "scope": scope,
                        "value": value,
                        "trade_count": len(scoped),
                        "mean_trades_per_month": len(scoped) / 12,
                        "coverage_eligible": minimum <= count <= maximum,
                    }
                )
        counts = (
            pd.to_datetime(frame["session_date"])
            .dt.to_period("M")
            .astype(str)
            .value_counts()
            .reindex(months, fill_value=0)
        )
        for month, month_count in counts.items():
            monthly_records.append(
                {
                    "filter_id": candidate.id,
                    "month": month,
                    "trade_count": int(month_count),
                }
            )
    return (
        pd.DataFrame.from_records(records),
        pd.DataFrame.from_records(monthly_records),
    )


def run_phase12_coverage(
    project_root: Path,
    *,
    artifact_root: Path | None = None,
) -> Phase12StageResult:
    """Run construction coverage screening without accessing P&L fields."""

    config = load_project_config(project_root / "config")
    parent_path = (
        project_root
        / "artifacts"
        / "phase1_1"
        / config.phase1_2.parent.fingerprint
        / "m15-structure-candidates.parquet"
    )
    if not parent_path.is_file():
        raise ValueError(f"Registered parent candidate artifact missing: {parent_path}")
    fingerprint, input_hashes = _stage_fingerprint(
        project_root, parent_path, "coverage"
    )
    parent = artifact_root or project_root / "artifacts" / "phase1_2" / "coverage"
    output = parent / fingerprint
    output.mkdir(parents=True, exist_ok=True)

    candidates = pd.read_parquet(parent_path, columns=list(SAFE_CANDIDATE_COLUMNS))
    construction = candidates[
        candidates["year"].eq(config.phase1_2.scope.construction_year)
    ].copy()
    selected_frames = [
        select_first_filter_candidates(construction, candidate.id, candidate.rules)
        for candidate in config.phase1_2.coverage_screen.candidates
    ]
    selected = pd.concat(selected_frames, ignore_index=True, sort=False)
    coverage, monthly = _coverage_tables(selected, config)
    failures = _coverage_invariant_failures(selected, construction, config)
    overall = coverage[coverage["scope"].eq("overall")]
    eligible = overall[overall["coverage_eligible"]]["filter_id"].tolist()

    summary = {
        "phase": config.phase1_2.phase,
        "stage": "construction_coverage_only",
        "fingerprint": fingerprint,
        "parent_fingerprint": config.phase1_2.parent.fingerprint,
        "construction_candidate_count": len(construction),
        "eligible_filters": eligible,
        "eligible_filter_count": len(eligible),
        "invariant_failure_count": sum(
            int(item.get("failure_count", 1)) for item in failures
        ),
        "invariant_failures": failures,
    }
    selected.to_parquet(output / "coverage-selected-signals.parquet", index=False)
    coverage.to_csv(output / "coverage.csv", index=False)
    monthly.to_csv(output / "monthly-counts.csv", index=False)
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    manifest = {
        "phase": config.phase1_2.phase,
        "stage": summary["stage"],
        "fingerprint": fingerprint,
        "created_at": datetime.now(UTC).isoformat(),
        "input_hashes": input_hashes,
        "safe_parent_columns": list(SAFE_CANDIDATE_COLUMNS),
        "artifact_files": sorted(path.name for path in output.iterdir()),
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return Phase12StageResult(artifact_directory=output, summary=summary)


def _construction_metrics(
    opportunities: pd.DataFrame,
    trades: pd.DataFrame,
    model_ids: tuple[str, ...],
) -> pd.DataFrame:
    records = []
    for model_id in model_ids:
        scoped = trades[trades["model_id"].eq(model_id)]
        net = scoped["net_r"]
        records.append(
            {
                "model_id": model_id,
                "opportunity_count": len(opportunities),
                "trade_count": len(scoped),
                "participation_rate": len(scoped) / len(opportunities),
                "total_net_r": float(net.sum()),
                "mean_trade_net_r": float(net.mean()) if len(net) else None,
                "win_rate": float(scoped["win"].mean()) if len(scoped) else None,
                "profit_factor": _profit_factor(net),
                "mean_opportunity_net_r": float(net.sum()) / len(opportunities),
            }
        )
    return pd.DataFrame.from_records(records)


def _construction_invariant_failures(
    signals: pd.DataFrame,
    trades: pd.DataFrame,
    config: ProjectConfig,
) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []

    def add(name: str, count: int) -> None:
        if count:
            failures.append({"invariant": name, "failure_count": int(count)})

    construction_year = config.phase1_2.scope.construction_year
    add("construction_signals_only", int(signals["year"].ne(construction_year).sum()))
    add("construction_trades_only", int(trades["year"].ne(construction_year).sum()))
    add(
        "one_trade_per_model_session",
        int(trades.duplicated(["model_id", "opportunity_id"]).sum()),
    )
    expected_counts = {
        item.id: item.trade_count
        for item in config.phase1_2_coverage_selection.eligible_filters
    }
    for model_id, expected in expected_counts.items():
        actual = int(signals["model_id"].eq(model_id).sum())
        add(f"{model_id}_matches_frozen_coverage", abs(actual - expected))
    allowed = {config.phase1_2.scope.baseline_model, *expected_counts}
    add("construction_models_frozen", int((~signals["model_id"].isin(allowed)).sum()))
    add(
        "entry_not_before_decision",
        int(trades["entry_at"].lt(trades["decision_at"]).sum()),
    )
    return failures


def run_phase12_construction(
    project_root: Path,
    data_root: Path,
    *,
    artifact_root: Path | None = None,
) -> Phase12StageResult:
    """Run 2024 P&L only for the frozen coverage-eligible filters."""

    config = load_project_config(project_root / "config")
    coverage_fingerprint = config.phase1_2_coverage_selection.coverage_fingerprint
    coverage_path = (
        project_root
        / "artifacts"
        / "phase1_2"
        / "coverage"
        / coverage_fingerprint
        / "coverage-selected-signals.parquet"
    )
    parent_directory = (
        project_root
        / "artifacts"
        / "phase1_1"
        / config.phase1_2.parent.fingerprint
    )
    parent_candidate_path = parent_directory / "m15-structure-candidates.parquet"
    parent_signal_path = parent_directory / "signals.parquet"
    parent_opportunity_path = parent_directory / "opportunities.parquet"
    required = (
        coverage_path,
        parent_candidate_path,
        parent_signal_path,
        parent_opportunity_path,
    )
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise ValueError("Phase 1.2 construction input missing: " + ", ".join(missing))

    input_paths = canonical_m5_paths(data_root, config.research)
    base_fingerprint, input_hashes = _fingerprint(project_root, input_paths)
    coverage_hash = _file_hash(coverage_path)
    digest = hashlib.sha256(
        f"construction:{base_fingerprint}:{coverage_hash}".encode()
    ).hexdigest()[:16]
    parent = (
        artifact_root or project_root / "artifacts" / "phase1_2" / "construction"
    )
    output = parent / digest
    output.mkdir(parents=True, exist_ok=True)

    eligible_ids = tuple(
        item.id for item in config.phase1_2_coverage_selection.eligible_filters
    )
    coverage_signals = pd.read_parquet(coverage_path)
    coverage_signals = coverage_signals[
        coverage_signals["filter_id"].isin(eligible_ids)
    ].copy()
    atr = pd.read_parquet(
        parent_candidate_path,
        columns=["opportunity_id", "source_event_id", "atr"],
    )
    filter_signals = coverage_signals.merge(
        atr,
        on=["opportunity_id", "source_event_id"],
        how="left",
        validate="many_to_one",
    )
    if filter_signals["atr"].isna().any():
        raise ValueError("Construction filter signal missing parent ATR")
    filter_signals["model_id"] = filter_signals["filter_id"]
    filter_signals["signal_id"] = filter_signals.apply(
        lambda row: f"signal:{row['filter_id']}:{row['opportunity_id']}", axis=1
    )
    filter_signals["signal_type"] = "phase1_2_light_filter"

    p3 = pd.read_parquet(parent_signal_path)
    p3 = p3[
        p3["model_id"].eq(config.phase1_2.scope.baseline_model)
        & p3["year"].eq(config.phase1_2.scope.construction_year)
    ].copy()
    signals = pd.concat([p3, filter_signals], ignore_index=True, sort=False)
    signals = signals.sort_values(
        ["decision_at", "model_id", "opportunity_id"], kind="stable"
    ).reset_index(drop=True)

    m5 = load_canonical_m5(data_root, config.research)
    construction_end = pd.Timestamp(config.research.periods.construction_end, tz="UTC")
    m5 = m5[m5["timestamp"].lt(construction_end)].reset_index(drop=True)
    trades = _simulate_signals(
        signals,
        m5,
        config,
        slippage_pips_per_side=config.execution.costs.slippage_pips_per_side,
    )
    opportunities = pd.read_parquet(parent_opportunity_path)
    opportunities = opportunities[
        opportunities["year"].eq(config.phase1_2.scope.construction_year)
    ].copy()
    model_ids = (config.phase1_2.scope.baseline_model, *eligible_ids)
    metrics = _construction_metrics(opportunities, trades, model_ids)
    baseline = metrics[
        metrics["model_id"].eq(config.phase1_2.scope.baseline_model)
    ].iloc[0]
    qualification_rows = []
    for model_id in eligible_ids:
        row = metrics[metrics["model_id"].eq(model_id)].iloc[0]
        checks = {
            "positive_mean_trade_net_r": bool(row["mean_trade_net_r"] > 0),
            "profit_factor_above_one": bool((row["profit_factor"] or 0) > 1),
            "mean_opportunity_improves_p3": bool(
                row["mean_opportunity_net_r"]
                > baseline["mean_opportunity_net_r"]
            ),
        }
        qualification_rows.append(
            {
                "filter_id": model_id,
                **checks,
                "qualified": all(checks.values()),
                "mean_opportunity_net_r": float(row["mean_opportunity_net_r"]),
            }
        )
    qualification = pd.DataFrame.from_records(qualification_rows)
    qualified = qualification[qualification["qualified"]]
    recommended_winner = None
    if not qualified.empty:
        order = {
            model_id: index
            for index, model_id in enumerate(
                config.phase1_2.construction_selection.tie_break_order
            )
        }
        qualified = qualified.assign(
            tie_order=qualified["filter_id"].map(order)
        ).sort_values(
            ["mean_opportunity_net_r", "tie_order"],
            ascending=[False, True],
            kind="stable",
        )
        recommended_winner = str(qualified.iloc[0]["filter_id"])

    failures = _construction_invariant_failures(signals, trades, config)
    summary = {
        "phase": config.phase1_2.phase,
        "stage": "construction_pnl",
        "fingerprint": digest,
        "coverage_fingerprint": coverage_fingerprint,
        "eligible_filters": list(eligible_ids),
        "qualified_filters": qualification[qualification["qualified"]][
            "filter_id"
        ].tolist(),
        "recommended_winner": recommended_winner,
        "replication_permitted": recommended_winner is not None and not failures,
        "invariant_failure_count": sum(
            int(item.get("failure_count", 1)) for item in failures
        ),
        "invariant_failures": failures,
    }
    signals.to_parquet(output / "construction-signals.parquet", index=False)
    trades.to_parquet(output / "construction-trades.parquet", index=False)
    metrics.to_csv(output / "construction-metrics.csv", index=False)
    qualification.to_csv(output / "construction-qualification.csv", index=False)
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    manifest = {
        "phase": config.phase1_2.phase,
        "stage": summary["stage"],
        "fingerprint": digest,
        "created_at": datetime.now(UTC).isoformat(),
        "input_hashes": {
            **input_hashes,
            "coverage-selected-signals.parquet": coverage_hash,
        },
        "artifact_files": sorted(path.name for path in output.iterdir()),
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return Phase12StageResult(artifact_directory=output, summary=summary)
