# GBPUSD Mechanical Structure Research

Reproducible research project for testing whether a point-in-time GBP-minus-USD
fundamental context and top-down market structure can produce a cost-aware,
mechanically executable GBPUSD edge.

The intended analysis chain is:

```text
fundamental context
        ↓
Daily / H4 / H1 regime
        ↓
mechanical support and resistance
        ↓
M15 setup: BOS / CHoCH / FVG
        ↓
M5 execution and risk management
```

Terms commonly associated with SMC are treated only as hypotheses. A concept is
not implemented until its geometry, confirmation delay, invalidation, and
execution timestamp can be expressed without discretionary chart reading or
future leakage.

## Current status

Phase 0 is active. It defines and validates labels; it does not trade.

- No strategy P&L has been inspected.
- BOS, CHoCH, FVG, swing, and S/R definitions are initial operational
  specifications whose stability will be measured without optimizing returns.
- Order blocks remain deferred until a reproducible definition survives a
  standalone label audit.
- EMA and RSI are registered as secondary ablations, not default confluence.

See:

- `docs/PRD_GBPUSD_MECHANICAL_STRUCTURE.md`
- `docs/TECHNICAL_PLAN_PHASE0.md`
- `docs/SHARED_DATA_CONTRACT.md`

## Setup

```bash
/opt/homebrew/bin/python3.12 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e '.[dev]'
```

Validate and inspect the frozen configuration:

```bash
.venv/bin/python -m gbpusd_structure config-check
.venv/bin/python -m gbpusd_structure show-config
.venv/bin/python -m gbpusd_structure data-root
```

Run checks:

```bash
.venv/bin/pytest
.venv/bin/ruff check .
```

## Data layout

Large data is never committed. By default this repository reads its gitignored
`data/` directory. To reuse the same canonical data without duplicating it, set:

```bash
export GBPUSD_SHARED_DATA_ROOT=/absolute/path/to/trading-data/gbpusd
```

The source repository `gbpusd-auction-value-volume-research` remains the audit
record for the earlier auction/value/volume hypotheses. This project imports
data contracts and selected point-in-time infrastructure, not conclusions or
strategy thresholds from that research.
