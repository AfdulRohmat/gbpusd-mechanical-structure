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
