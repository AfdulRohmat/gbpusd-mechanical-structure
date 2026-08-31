"""Command-line entry point for project configuration and data contracts."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from pydantic import ValidationError

from gbpusd_structure.config import load_project_config, resolve_data_root
from gbpusd_structure.data import audit_canonical_m5, load_canonical_m5
from gbpusd_structure.m1 import build_m1_year, load_m1_year, reconcile_m1_to_m5
from gbpusd_structure.paths import find_project_root
from gbpusd_structure.phase0 import run_phase0_2
from gbpusd_structure.phase1 import run_phase1, run_phase1_1
from gbpusd_structure.phase2 import run_phase2_directional_audit
from gbpusd_structure.phase3 import run_phase3_state_coverage
from gbpusd_structure.phase12 import (
    run_phase12_construction,
    run_phase12_coverage,
)
from gbpusd_structure.phase13 import run_phase1_3
from gbpusd_structure.phase14 import run_phase1_4_construction
from gbpusd_structure.phase15 import (
    run_phase1_5_construction,
    run_phase1_5_coverage,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gbpusd-structure")
    parser.add_argument(
        "--config-directory",
        type=Path,
        default=Path("config"),
        help="configuration directory relative to the project root",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("config-check", help="validate every checked-in config")
    subparsers.add_parser("show-config", help="print normalized configuration")
    data_root = subparsers.add_parser(
        "data-root", help="show the resolved shared/local data directory"
    )
    data_root.add_argument(
        "--require-exists",
        action="store_true",
        help="return an error when the resolved directory does not exist",
    )
    subparsers.add_parser(
        "audit-data",
        help="audit canonical M5 coverage, schema, and observed spread proxy",
    )
    phase0 = subparsers.add_parser(
        "run-phase0-2",
        help="run causal Order Block definition audit without P&L",
    )
    phase0.add_argument(
        "--artifact-root",
        type=Path,
        help="optional artifact parent; fingerprint is appended automatically",
    )
    phase1 = subparsers.add_parser(
        "run-phase1",
        help="run preregistered nested price baselines with full costs",
    )
    phase1.add_argument(
        "--artifact-root",
        type=Path,
        help="optional artifact parent; fingerprint is appended automatically",
    )
    phase1_1 = subparsers.add_parser(
        "run-phase1-1",
        help="run the preregistered full-session setup revision",
    )
    phase1_1.add_argument(
        "--artifact-root",
        type=Path,
        help="optional artifact parent; fingerprint is appended automatically",
    )
    phase12_coverage = subparsers.add_parser(
        "run-phase1-2-coverage",
        help="screen construction coverage without accessing P&L",
    )
    phase12_coverage.add_argument(
        "--artifact-root",
        type=Path,
        help="optional artifact parent; fingerprint is appended automatically",
    )
    phase12_construction = subparsers.add_parser(
        "run-phase1-2-construction",
        help="run 2024 P&L for frozen coverage-eligible filters only",
    )
    phase12_construction.add_argument(
        "--artifact-root",
        type=Path,
        help="optional artifact parent; fingerprint is appended automatically",
    )
    phase13 = subparsers.add_parser(
        "run-phase1-3",
        help="run the P3 MAE/MFE and stop-adequacy path audit",
    )
    phase13.add_argument(
        "--artifact-root",
        type=Path,
        help="optional artifact parent; fingerprint is appended automatically",
    )
    phase14_construction = subparsers.add_parser(
        "run-phase1-4-construction",
        help="run 2024 structural-invalidation stop construction ablation",
    )
    phase14_construction.add_argument(
        "--artifact-root",
        type=Path,
        help="optional artifact parent; fingerprint is appended automatically",
    )
    phase15_m1 = subparsers.add_parser(
        "build-phase1-5-m1",
        help="build and reconcile construction M1 bars from local tick archives",
    )
    phase15_m1.add_argument("--year", type=int, default=2024)
    phase15_m1.add_argument("--force", action="store_true")
    phase15_coverage = subparsers.add_parser(
        "run-phase1-5-coverage",
        help="run return-blind 2024 M5/M1 FVG entry coverage",
    )
    phase15_coverage.add_argument(
        "--artifact-root",
        type=Path,
        help="optional artifact parent; fingerprint is appended automatically",
    )
    phase15_construction = subparsers.add_parser(
        "run-phase1-5-construction",
        help="run 2024 P&L for frozen FVG entry candidates",
    )
    phase15_construction.add_argument(
        "--artifact-root",
        type=Path,
        help="optional artifact parent; fingerprint is appended automatically",
    )
    phase2 = subparsers.add_parser(
        "run-phase2-directional-audit",
        help="run the preregistered 2024 gross directional primitive audit",
    )
    phase2.add_argument(
        "--artifact-root",
        type=Path,
        help="optional artifact parent; fingerprint is appended automatically",
    )
    phase3 = subparsers.add_parser(
        "run-phase3-state-coverage",
        help="run return-blind 2024 price-action state/setup coverage",
    )
    phase3.add_argument(
        "--artifact-root",
        type=Path,
        help="optional artifact parent; fingerprint is appended automatically",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        project_root = find_project_root(Path.cwd())
        config_directory = (
            args.config_directory
            if args.config_directory.is_absolute()
            else project_root / args.config_directory
        )
        config = load_project_config(config_directory)
    except (ValueError, ValidationError) as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    if args.command == "config-check":
        print("Configuration valid")
        return 0
    if args.command == "show-config":
        print(json.dumps(config.model_dump(mode="json"), indent=2, sort_keys=True))
        return 0
    if args.command == "data-root":
        root = resolve_data_root(project_root, config.research.data)
        if args.require_exists and not root.is_dir():
            print(f"Data root does not exist: {root}", file=sys.stderr)
            return 1
        print(root)
        return 0
    if args.command == "audit-data":
        root = resolve_data_root(project_root, config.research.data)
        if not root.is_dir():
            print(f"Data root does not exist: {root}", file=sys.stderr)
            return 1
        summary = audit_canonical_m5(root, config.research)
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0 if summary["valid"] else 1
    if args.command == "run-phase0-2":
        root = resolve_data_root(project_root, config.research.data)
        if not root.is_dir():
            print(f"Data root does not exist: {root}", file=sys.stderr)
            return 1
        artifact_root = args.artifact_root
        if artifact_root is not None and not artifact_root.is_absolute():
            artifact_root = project_root / artifact_root
        try:
            result = run_phase0_2(
                project_root,
                root,
                artifact_root=artifact_root,
            )
        except (OSError, ValueError) as exc:
            print(f"Phase 0.2 failed: {exc}", file=sys.stderr)
            return 1
        output = {
            "artifact_directory": str(result.artifact_directory),
            "gate_passed": result.summary["gate"]["passed"],
            "failed_gate_count": result.summary["gate"]["failed_count"],
            "point_in_time_failures": result.summary["point_in_time_failures"],
        }
        print(json.dumps(output, indent=2, sort_keys=True))
        return 0 if result.summary["gate"]["passed"] else 1
    if args.command == "run-phase1":
        root = resolve_data_root(project_root, config.research.data)
        if not root.is_dir():
            print(f"Data root does not exist: {root}", file=sys.stderr)
            return 1
        artifact_root = args.artifact_root
        if artifact_root is not None and not artifact_root.is_absolute():
            artifact_root = project_root / artifact_root
        try:
            result = run_phase1(
                project_root,
                root,
                artifact_root=artifact_root,
            )
        except (OSError, ValueError) as exc:
            print(f"Phase 1 failed: {exc}", file=sys.stderr)
            return 1
        output = {
            "artifact_directory": str(result.artifact_directory),
            "any_candidate_passed": result.summary["any_candidate_passed"],
            "invariant_failure_count": result.summary[
                "invariant_failure_count"
            ],
            "signal_counts": result.summary["signal_counts"],
        }
        print(json.dumps(output, indent=2, sort_keys=True))
        return 0 if result.summary["any_candidate_passed"] else 1
    if args.command == "run-phase1-1":
        root = resolve_data_root(project_root, config.research.data)
        if not root.is_dir():
            print(f"Data root does not exist: {root}", file=sys.stderr)
            return 1
        artifact_root = args.artifact_root
        if artifact_root is not None and not artifact_root.is_absolute():
            artifact_root = project_root / artifact_root
        try:
            result = run_phase1_1(
                project_root,
                root,
                artifact_root=artifact_root,
            )
        except (OSError, ValueError) as exc:
            print(f"Phase 1.1 failed: {exc}", file=sys.stderr)
            return 1
        output = {
            "artifact_directory": str(result.artifact_directory),
            "any_candidate_passed": result.summary["any_candidate_passed"],
            "invariant_failure_count": result.summary[
                "invariant_failure_count"
            ],
            "signal_counts": result.summary["signal_counts"],
            "alignment_funnel": result.summary["alignment_funnel"],
        }
        print(json.dumps(output, indent=2, sort_keys=True))
        return 0 if result.summary["any_candidate_passed"] else 1
    if args.command == "run-phase1-2-coverage":
        artifact_root = args.artifact_root
        if artifact_root is not None and not artifact_root.is_absolute():
            artifact_root = project_root / artifact_root
        try:
            result = run_phase12_coverage(
                project_root,
                artifact_root=artifact_root,
            )
        except (OSError, ValueError) as exc:
            print(f"Phase 1.2 coverage failed: {exc}", file=sys.stderr)
            return 1
        output = {
            "artifact_directory": str(result.artifact_directory),
            "eligible_filters": result.summary["eligible_filters"],
            "invariant_failure_count": result.summary[
                "invariant_failure_count"
            ],
        }
        print(json.dumps(output, indent=2, sort_keys=True))
        return 0 if (
            result.summary["eligible_filter_count"] > 0
            and result.summary["invariant_failure_count"] == 0
        ) else 1
    if args.command == "run-phase1-2-construction":
        root = resolve_data_root(project_root, config.research.data)
        if not root.is_dir():
            print(f"Data root does not exist: {root}", file=sys.stderr)
            return 1
        artifact_root = args.artifact_root
        if artifact_root is not None and not artifact_root.is_absolute():
            artifact_root = project_root / artifact_root
        try:
            result = run_phase12_construction(
                project_root,
                root,
                artifact_root=artifact_root,
            )
        except (OSError, ValueError) as exc:
            print(f"Phase 1.2 construction failed: {exc}", file=sys.stderr)
            return 1
        output = {
            "artifact_directory": str(result.artifact_directory),
            "qualified_filters": result.summary["qualified_filters"],
            "recommended_winner": result.summary["recommended_winner"],
            "replication_permitted": result.summary["replication_permitted"],
            "invariant_failure_count": result.summary[
                "invariant_failure_count"
            ],
        }
        print(json.dumps(output, indent=2, sort_keys=True))
        return 0 if result.summary["replication_permitted"] else 1
    if args.command == "run-phase1-3":
        root = resolve_data_root(project_root, config.research.data)
        if not root.is_dir():
            print(f"Data root does not exist: {root}", file=sys.stderr)
            return 1
        artifact_root = args.artifact_root
        if artifact_root is not None and not artifact_root.is_absolute():
            artifact_root = project_root / artifact_root
        try:
            result = run_phase1_3(
                project_root,
                root,
                artifact_root=artifact_root,
            )
        except (OSError, ValueError) as exc:
            print(f"Phase 1.3 failed: {exc}", file=sys.stderr)
            return 1
        output = {
            "artifact_directory": str(result.artifact_directory),
            "signal_count": result.summary["signal_count"],
            "invariant_failure_count": result.summary[
                "invariant_failure_count"
            ],
            "original_1atr_2atr_path": result.summary[
                "original_1atr_2atr_path"
            ],
        }
        print(json.dumps(output, indent=2, sort_keys=True))
        return 0 if result.summary["invariant_failure_count"] == 0 else 1
    if args.command == "run-phase1-4-construction":
        root = resolve_data_root(project_root, config.research.data)
        if not root.is_dir():
            print(f"Data root does not exist: {root}", file=sys.stderr)
            return 1
        artifact_root = args.artifact_root
        if artifact_root is not None and not artifact_root.is_absolute():
            artifact_root = project_root / artifact_root
        try:
            result = run_phase1_4_construction(
                project_root,
                root,
                artifact_root=artifact_root,
            )
        except (OSError, ValueError) as exc:
            print(f"Phase 1.4 construction failed: {exc}", file=sys.stderr)
            return 1
        output = {
            "artifact_directory": str(result.artifact_directory),
            "signal_count": result.summary["signal_count"],
            "invariant_failure_count": result.summary[
                "invariant_failure_count"
            ],
            "construction_gate": result.summary["construction_gate"],
            "replication_permitted": result.summary["replication_permitted"],
        }
        print(json.dumps(output, indent=2, sort_keys=True))
        return 0 if result.summary["replication_permitted"] else 1
    if args.command == "build-phase1-5-m1":
        root = resolve_data_root(project_root, config.research.data)
        if not root.is_dir():
            print(f"Data root does not exist: {root}", file=sys.stderr)
            return 1
        try:
            summary = build_m1_year(root, config, args.year, force=args.force)
            m1 = load_m1_year(root, config, args.year)
            m5 = load_canonical_m5(root, config.research)
            m5 = m5[m5["timestamp"].dt.year.eq(args.year)].reset_index(drop=True)
            reconciliation = reconcile_m1_to_m5(m1, m5)
        except (OSError, ValueError) as exc:
            print(f"Phase 1.5 M1 build failed: {exc}", file=sys.stderr)
            return 1
        output = {
            "audit_path": summary["audit_path"],
            "year": args.year,
            "month_count": summary["month_count"],
            "m1_bar_count": len(m1),
            "reconciliation": reconciliation,
        }
        print(json.dumps(output, indent=2, sort_keys=True))
        return 0 if reconciliation["valid"] else 1
    if args.command == "run-phase1-5-coverage":
        root = resolve_data_root(project_root, config.research.data)
        if not root.is_dir():
            print(f"Data root does not exist: {root}", file=sys.stderr)
            return 1
        artifact_root = args.artifact_root
        if artifact_root is not None and not artifact_root.is_absolute():
            artifact_root = project_root / artifact_root
        try:
            result = run_phase1_5_coverage(
                project_root,
                root,
                artifact_root=artifact_root,
            )
        except (OSError, ValueError) as exc:
            print(f"Phase 1.5 coverage failed: {exc}", file=sys.stderr)
            return 1
        output = {
            "artifact_directory": str(result.artifact_directory),
            "entry_counts": result.summary["entry_counts"],
            "eligible_candidates": result.summary["eligible_candidates"],
            "invariant_failure_count": result.summary[
                "invariant_failure_count"
            ],
            "construction_pnl_permitted": result.summary[
                "construction_pnl_permitted"
            ],
        }
        print(json.dumps(output, indent=2, sort_keys=True))
        return 0 if result.summary["construction_pnl_permitted"] else 1
    if args.command == "run-phase1-5-construction":
        root = resolve_data_root(project_root, config.research.data)
        if not root.is_dir():
            print(f"Data root does not exist: {root}", file=sys.stderr)
            return 1
        artifact_root = args.artifact_root
        if artifact_root is not None and not artifact_root.is_absolute():
            artifact_root = project_root / artifact_root
        try:
            result = run_phase1_5_construction(
                project_root,
                root,
                artifact_root=artifact_root,
            )
        except (OSError, ValueError) as exc:
            print(f"Phase 1.5 construction failed: {exc}", file=sys.stderr)
            return 1
        output = {
            "artifact_directory": str(result.artifact_directory),
            "invariant_failure_count": result.summary[
                "invariant_failure_count"
            ],
            "qualified_candidates": result.summary["qualified_candidates"],
            "recommended_winner": result.summary["recommended_winner"],
            "replication_permitted": result.summary["replication_permitted"],
        }
        print(json.dumps(output, indent=2, sort_keys=True))
        return 0 if result.summary["replication_permitted"] else 1
    if args.command == "run-phase2-directional-audit":
        root = resolve_data_root(project_root, config.research.data)
        if not root.is_dir():
            print(f"Data root does not exist: {root}", file=sys.stderr)
            return 1
        artifact_root = args.artifact_root
        if artifact_root is not None and not artifact_root.is_absolute():
            artifact_root = project_root / artifact_root
        try:
            result = run_phase2_directional_audit(
                project_root,
                root,
                artifact_root=artifact_root,
            )
        except (OSError, ValueError) as exc:
            print(f"Phase 2 directional audit failed: {exc}", file=sys.stderr)
            return 1
        output = {
            "artifact_directory": str(result.artifact_directory),
            "invariant_failure_count": result.summary["invariant_failure_count"],
            "primary_event_counts": result.summary["primary_event_counts"],
            "qualified_primitives": result.summary["qualified_primitives"],
            "recommended_winner": result.summary["recommended_winner"],
            "decision": result.summary["decision"],
        }
        print(json.dumps(output, indent=2, sort_keys=True))
        return 0 if result.summary["invariant_failure_count"] == 0 else 1
    if args.command == "run-phase3-state-coverage":
        root = resolve_data_root(project_root, config.research.data)
        if not root.is_dir():
            print(f"Data root does not exist: {root}", file=sys.stderr)
            return 1
        artifact_root = args.artifact_root
        if artifact_root is not None and not artifact_root.is_absolute():
            artifact_root = project_root / artifact_root
        try:
            result = run_phase3_state_coverage(
                project_root,
                root,
                artifact_root=artifact_root,
            )
        except (OSError, ValueError) as exc:
            print(f"Phase 3 state coverage failed: {exc}", file=sys.stderr)
            return 1
        output = {
            "artifact_directory": str(result.artifact_directory),
            "invariant_failure_count": result.summary[
                "invariant_failure_count"
            ],
            "coverage": result.summary["coverage"],
            "coverage_gate": result.summary["coverage_gate"],
            "construction_pnl_permitted": result.summary[
                "construction_pnl_permitted"
            ],
            "decision": result.summary["decision"],
        }
        print(json.dumps(output, indent=2, sort_keys=True))
        return 0 if result.summary["invariant_failure_count"] == 0 else 1
    raise AssertionError(f"Unhandled command: {args.command}")
