"""Auditable HistData tick-to-M1 adapter for Phase 1.5."""

from __future__ import annotations

import hashlib
import json
import zipfile
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from gbpusd_structure.config import ProjectConfig

SOURCE_TIMEZONE = "Etc/GMT+5"
M1_REQUIRED_COLUMNS = {
    "timestamp",
    "bid_open",
    "bid_high",
    "bid_low",
    "bid_close",
    "ask_open",
    "ask_high",
    "ask_low",
    "ask_close",
    "mid_open",
    "mid_high",
    "mid_low",
    "mid_close",
    "tick_count",
    "activity_count",
    "spread_open_pips",
    "spread_median_pips",
    "spread_p95_pips",
    "spread_max_pips",
    "first_tick_timestamp",
    "last_tick_timestamp",
}


def histdata_archive_path(
    data_root: Path,
    symbol: str,
    year: int,
    month: int,
) -> Path:
    name = f"HISTDATA_COM_ASCII_{symbol.upper()}_T{year:04d}{month:02d}.zip"
    return data_root / "raw" / "histdata" / symbol.upper() / str(year) / name


def m1_month_path(
    data_root: Path,
    symbol: str,
    year: int,
    month: int,
) -> Path:
    return (
        data_root
        / "processed"
        / "m1_monthly"
        / f"symbol={symbol.upper()}"
        / f"year={year:04d}"
        / f"m1-{year:04d}-{month:02d}.parquet"
    )


def _archive_member(path: Path) -> str:
    try:
        with zipfile.ZipFile(path) as archive:
            members = [
                name for name in archive.namelist() if name.lower().endswith(".csv")
            ]
            if len(members) != 1:
                raise ValueError(
                    f"Expected one HistData CSV in {path.name}, found {len(members)}"
                )
            return members[0]
    except zipfile.BadZipFile as exc:
        raise ValueError(f"Invalid HistData ZIP: {path}") from exc


def iter_histdata_ticks(
    path: Path,
    *,
    pip_size: float,
    chunksize: int = 500_000,
) -> Iterator[pd.DataFrame]:
    """Yield normalized UTC Bid/Ask tick chunks from one local archive."""

    member = _archive_member(path)
    with zipfile.ZipFile(path) as archive, archive.open(member) as stream:
        chunks = pd.read_csv(
            stream,
            header=None,
            names=["source_timestamp", "bid", "ask", "source_volume"],
            dtype={
                "source_timestamp": "string",
                "bid": "float64",
                "ask": "float64",
                "source_volume": "float32",
            },
            chunksize=chunksize,
        )
        for chunk in chunks:
            local = pd.to_datetime(
                chunk.pop("source_timestamp"),
                format="%Y%m%d %H%M%S%f",
                errors="raise",
            ).dt.tz_localize(SOURCE_TIMEZONE)
            chunk.insert(0, "timestamp", local.dt.tz_convert("UTC"))
            chunk["mid"] = (chunk["bid"] + chunk["ask"]) / 2
            chunk["spread_pips"] = (
                (chunk["ask"] - chunk["bid"]) / pip_size
            ).astype("float32")
            chunk["activity"] = 1
            yield chunk[
                ["timestamp", "bid", "ask", "mid", "spread_pips", "activity"]
            ]


def read_histdata_archive(path: Path, *, pip_size: float) -> pd.DataFrame:
    frames = list(iter_histdata_ticks(path, pip_size=pip_size))
    if not frames:
        raise ValueError(f"HistData archive contains no ticks: {path}")
    return (
        pd.concat(frames, ignore_index=True)
        .sort_values("timestamp", kind="stable")
        .drop_duplicates()
        .reset_index(drop=True)
    )


def resample_ticks_m1(ticks: pd.DataFrame) -> pd.DataFrame:
    if ticks.empty:
        raise ValueError("Cannot resample empty ticks to M1")
    ordered = ticks.sort_values("timestamp", kind="stable")
    indexed = ordered.set_index("timestamp")
    outputs: list[pd.DataFrame | pd.Series] = []
    for side in ("bid", "ask", "mid"):
        ohlc = indexed[side].resample("1min", label="left", closed="left").ohlc()
        ohlc.columns = [f"{side}_{column}" for column in ohlc.columns]
        outputs.append(ohlc)
    grouped = indexed.resample("1min", label="left", closed="left")
    indexed["_tick_timestamp"] = indexed.index
    outputs.extend(
        [
            grouped.size().rename("tick_count"),
            grouped["activity"].sum(min_count=1).rename("activity_count"),
            grouped["spread_pips"].first().rename("spread_open_pips"),
            grouped["spread_pips"].median().rename("spread_median_pips"),
            grouped["spread_pips"].quantile(0.95).rename("spread_p95_pips"),
            grouped["spread_pips"].max().rename("spread_max_pips"),
            grouped["_tick_timestamp"].min().rename("first_tick_timestamp"),
            grouped["_tick_timestamp"].max().rename("last_tick_timestamp"),
        ]
    )
    bars = pd.concat(outputs, axis=1)
    bars = bars[bars["tick_count"].gt(0)].copy()
    bars.insert(0, "timestamp", bars.index)
    return bars.reset_index(drop=True)


def _validate_m1(bars: pd.DataFrame) -> dict[str, Any]:
    missing = sorted(M1_REQUIRED_COLUMNS.difference(bars.columns))
    violations = {}
    for side in ("bid", "ask", "mid"):
        high = bars[f"{side}_high"]
        low = bars[f"{side}_low"]
        opened = bars[f"{side}_open"]
        closed = bars[f"{side}_close"]
        violations[side] = int(
            (
                high.lt(low)
                | high.lt(opened)
                | high.lt(closed)
                | low.gt(opened)
                | low.gt(closed)
            ).sum()
        )
    timestamps = pd.to_datetime(bars["timestamp"], utc=True)
    return {
        "valid": bool(
            len(bars)
            and not missing
            and not sum(violations.values())
            and not timestamps.duplicated().any()
            and timestamps.is_monotonic_increasing
        ),
        "bar_count": len(bars),
        "missing_columns": missing,
        "ohlc_violation_count": violations,
        "duplicate_timestamp_count": int(timestamps.duplicated().sum()),
        "utc_aware": str(timestamps.dt.tz) == "UTC",
        "monotonic": bool(timestamps.is_monotonic_increasing),
        "first_timestamp": timestamps.min().isoformat(),
        "last_timestamp": timestamps.max().isoformat(),
    }


def _atomic_parquet(frame: pd.DataFrame, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".parquet.part")
    frame.to_parquet(temporary, index=False)
    temporary.replace(destination)


def build_m1_year(
    data_root: Path,
    config: ProjectConfig,
    year: int,
    *,
    force: bool = False,
) -> dict[str, Any]:
    symbol = config.research.instrument.symbol
    pip_size = config.research.instrument.pip_size
    monthly = []
    source_hashes = {}
    for month in range(1, 13):
        source = histdata_archive_path(data_root, symbol, year, month)
        if not source.is_file():
            raise ValueError(f"Missing HistData tick archive: {source}")
        destination = m1_month_path(data_root, symbol, year, month)
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        source_hashes[source.name] = digest
        if destination.is_file() and not force:
            bars = pd.read_parquet(destination)
            status = "cached"
        else:
            ticks = read_histdata_archive(source, pip_size=pip_size)
            bars = resample_ticks_m1(ticks)
            _atomic_parquet(bars, destination)
            status = "built"
        quality = _validate_m1(bars)
        if not quality["valid"]:
            raise ValueError(f"Invalid M1 output for {year:04d}-{month:02d}: {quality}")
        monthly.append(
            {
                "month": f"{year:04d}-{month:02d}",
                "status": status,
                "output": str(destination.relative_to(data_root)),
                **quality,
            }
        )

    summary = {
        "phase": "phase1_5_fvg_pullback_entry",
        "year": year,
        "source": "histdata_tick_archives",
        "source_timezone": SOURCE_TIMEZONE,
        "generated_at": datetime.now(UTC).isoformat(),
        "source_hashes": source_hashes,
        "month_count": len(monthly),
        "bar_count": sum(item["bar_count"] for item in monthly),
        "months": monthly,
    }
    audit_path = (
        data_root
        / "processed"
        / "m1_monthly"
        / f"symbol={symbol}"
        / f"year={year:04d}"
        / f"audit-{year:04d}.json"
    )
    audit_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    summary["audit_path"] = str(audit_path)
    return summary


def load_m1_year(
    data_root: Path,
    config: ProjectConfig,
    year: int,
) -> pd.DataFrame:
    symbol = config.research.instrument.symbol
    paths = [m1_month_path(data_root, symbol, year, month) for month in range(1, 13)]
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        raise ValueError("Missing Phase 1.5 M1 files: " + ", ".join(missing))
    bars = pd.concat([pd.read_parquet(path) for path in paths], ignore_index=True)
    bars["timestamp"] = pd.to_datetime(bars["timestamp"], utc=True)
    bars = bars[bars["timestamp"].dt.year.eq(year)]
    return (
        bars.sort_values("timestamp", kind="stable")
        .drop_duplicates("timestamp", keep="last")
        .reset_index(drop=True)
    )


def reconcile_m1_to_m5(
    m1: pd.DataFrame,
    m5: pd.DataFrame,
) -> dict[str, Any]:
    indexed = m1.set_index("timestamp")
    outputs: list[pd.Series] = []
    for side in ("bid", "ask", "mid"):
        grouped = indexed.resample("5min", label="left", closed="left")
        outputs.extend(
            [
                grouped[f"{side}_open"].first().rename(f"{side}_open"),
                grouped[f"{side}_high"].max().rename(f"{side}_high"),
                grouped[f"{side}_low"].min().rename(f"{side}_low"),
                grouped[f"{side}_close"].last().rename(f"{side}_close"),
            ]
        )
    grouped = indexed.resample("5min", label="left", closed="left")
    outputs.append(grouped["tick_count"].sum(min_count=1).rename("tick_count"))
    rebuilt = pd.concat(outputs, axis=1).dropna().reset_index()
    canonical = m5.copy()
    canonical["timestamp"] = pd.to_datetime(canonical["timestamp"], utc=True)
    columns = ["timestamp", *[column for column in rebuilt if column != "timestamp"]]
    joined = rebuilt[columns].merge(
        canonical[columns],
        on="timestamp",
        how="outer",
        suffixes=("_m1", "_m5"),
        indicator=True,
    )
    membership_failures = int(joined["_merge"].ne("both").sum())
    mismatches: dict[str, int] = {}
    for column in columns[1:]:
        left = joined[f"{column}_m1"]
        right = joined[f"{column}_m5"]
        if column == "tick_count":
            equal = left.eq(right)
        else:
            equal = np.isclose(left, right, rtol=0, atol=1e-12, equal_nan=False)
        mismatches[column] = int((~equal).sum())
    return {
        "valid": not membership_failures and not sum(mismatches.values()),
        "rebuilt_m5_count": len(rebuilt),
        "canonical_m5_count": len(canonical),
        "membership_failure_count": membership_failures,
        "column_mismatch_count": mismatches,
    }

