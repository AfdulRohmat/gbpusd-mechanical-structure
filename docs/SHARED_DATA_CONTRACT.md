# Shared GBPUSD Data Contract

## Purpose

Both GBPUSD repositories should read one local canonical dataset without
duplicating large tick or Parquet files. Git stores schemas, code, configuration,
and manifests—not raw market data.

## Root selection

The new repository resolves its data root as follows:

1. `GBPUSD_SHARED_DATA_ROOT`, when set; otherwise
2. the repository-local, gitignored `data/` directory.

Recommended layout:

```text
research/
├── trading-data/
│   └── gbpusd/
│       ├── raw/
│       │   └── exness/
│       ├── processed/
│       │   ├── m5_monthly/symbol=GBPUSD/year=YYYY/  # temporary HistData
│       │   └── exness/m5_monthly/symbol=GBPUSD/year=YYYY/  # future
│       ├── reference/
│       │   └── fundamentals/
│       └── manifests/
├── gbpusd-auction-value-volume-research/
└── gbpusd-mechanical-structure/
```

## Canonical M5 requirements

Temporary monthly Parquet partitions use:

```text
processed/m5_monthly/symbol=GBPUSD/year=YYYY/m5-YYYY-MM.parquet
```

Account-aligned Exness partitions will later use the `processed/exness/` prefix.

Required columns:

```text
timestamp
bid_open, bid_high, bid_low, bid_close
ask_open, ask_high, ask_low, ask_close
mid_open, mid_high, mid_low, mid_close
tick_count, activity_count
up_quote_count, down_quote_count, flat_quote_count
spread_open_pips, spread_median_pips, spread_p95_pips, spread_max_pips
first_tick_timestamp, last_tick_timestamp
```

- `timestamp` is UTC-aware and denotes the left edge of a five-minute bucket.
- Bid/Ask columns drive execution; mid columns are analytical.
- Quote counts are broker-feed activity, not centralized traded volume.
- Partitions are sorted and unique by timestamp.
- Source hashes and coverage summaries live in `manifests/`.

## Fundamental requirements

Point-in-time tables live under `reference/fundamentals/`. Every observation
must include:

```text
event_timestamp
available_at
currency
component
actual
consensus (nullable)
previous (nullable)
source
source_recorded_at
```

Derived fundamental scores must retain their contributing source row IDs. A
revised economic observation cannot overwrite the value that was available at
the historical decision time.

## Ownership

- Raw Exness archives are immutable inputs.
- The auction/value/volume repository remains the producer of the current
  canonical Exness M5 contract until extraction is moved into a dedicated data
  package.
- The mechanical-structure repository consumes canonical M5 read-only and owns
  its higher-timeframe bars, structure labels, models, and reports.
- Generated artifacts include source/config/code fingerprints for audit.
