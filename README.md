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

Phase 0.1 has been executed. It defines and validates labels; it does not trade.
The refined swing and protected-structure state machine passed its registered
gates with zero point-in-time failures. H1 S/R remains excluded because one
sensitivity scored 69.69% against the frozen 70% requirement; H4 S/R passed.

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
- `docs/TEMPORARY_EXECUTION_MODEL.md`
- `docs/DATA_BASELINE_2024_2025.md`
- `docs/PHASE0_RESULTS.md`
- `docs/TECHNICAL_PLAN_PHASE0_1.md`
- `docs/PHASE0_1_RESULTS.md`
- `docs/TECHNICAL_PLAN_PHASE0_2.md`

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

## Temporary execution source

During Phase 0, the local `data/` path points to the existing 2024–2025 GBPUSD
dataset from the auction/value/volume project. No market data is duplicated.

- Price and structure use the existing HistData-derived M5 bars.
- Execution uses their observed historical Bid/Ask spread as a conservative
  proxy; it is not labeled as an Exness spread.
- Raw Spread commission is modeled at USD 3.50/lot/side (`0.35` pip/side for
  one standard GBPUSD lot).
- Primary slippage is `0.10` pip/side, with `0.20` pip/side registered stress.
- When account-aligned Exness MT5 data becomes available, only the data and
  pricing adapter changes; the structure definitions remain frozen.

Audit the linked dataset with:

```bash
.venv/bin/python -m gbpusd_structure audit-data
```

Run the current Phase-0.1 definition audit (no trades and no P&L):

```bash
.venv/bin/python -m gbpusd_structure run-phase0-1
```

The command writes fingerprinted, gitignored tables and reports below
`artifacts/phase0_1/`. A non-zero exit status means at least one registered
definition gate failed; it does not mean the command crashed. Inspect that
run's `summary.json` for the exact failed scopes.
