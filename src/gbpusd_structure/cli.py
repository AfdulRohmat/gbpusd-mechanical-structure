"""Command-line entry point for project configuration and data contracts."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from pydantic import ValidationError

from gbpusd_structure.config import load_project_config, resolve_data_root
from gbpusd_structure.paths import find_project_root


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
    raise AssertionError(f"Unhandled command: {args.command}")
