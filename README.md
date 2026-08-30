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

Phase 1.2 tested whether light causal filters could reduce full-session P3 from
approximately 32 to 20–25 trades per month while improving quality. A staged
lock screened coverage before P&L and allowed only displacement (F1) and a
non-opposition H1+H4 veto (F4) into 2024 construction.

The frequency target was reached, but neither filter was positive. F1 produced
275 trades at `-0.346R/trade`; F4 produced 288 at `-0.230R/trade`. No filter
qualified for selection, so 2025 filter P&L remained unopened by design.

- The Phase-1.1 run had zero point-in-time, session, parent, or execution
  invariant failures.
- H1 S/R remains excluded after its Phase-0.1 stability failure.
- Order Blocks remain diagnostic only after the Phase-0.2 geometry failure and
  were not used anywhere in Phase 1 or Phase 1.1.
- Fundamentals, EMA, and RSI remain untested incremental layers.

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
- `docs/PHASE0_2_RESULTS.md`
- `docs/TECHNICAL_PLAN_PHASE1.md`
- `docs/PHASE1_RESULTS.md`
- `docs/TECHNICAL_PLAN_PHASE1_1.md`
- `docs/PHASE1_1_RESULTS.md`
- `docs/TECHNICAL_PLAN_PHASE1_2.md`
- `docs/PHASE1_2_COVERAGE_RESULTS.md`
- `docs/PHASE1_2_RESULTS.md`

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

Run the current Phase-0.2 Order Block definition audit (no trades and no P&L):

```bash
.venv/bin/python -m gbpusd_structure run-phase0-2
```

The command writes fingerprinted, gitignored tables and reports below
`artifacts/phase0_2/`. A non-zero exit status means at least one registered
definition gate failed; it does not mean the command crashed. Inspect that
run's `summary.json` for the exact failed scopes.

Run the preregistered Phase-1 nested price baselines:

```bash
.venv/bin/python -m gbpusd_structure run-phase1
```

The official run writes to `artifacts/phase1/daac4b3ee86ac545/`. The command
returns non-zero when no advancement candidate passes; this is a research-gate
result, not a simulator crash.

Run the full-session Phase-1.1 revision:

```bash
.venv/bin/python -m gbpusd_structure run-phase1-1
```

Its official evidence is under `artifacts/phase1_1/90d1e369b427d3d8/`. Phase 1
remains preserved as the opening-window parent rather than being overwritten.

Run the staged Phase-1.2 construction study:

```bash
.venv/bin/python -m gbpusd_structure run-phase1-2-coverage
.venv/bin/python -m gbpusd_structure run-phase1-2-construction
```

The construction command returns non-zero because no filter qualified for
replication. No replication command or winner file exists for this run.

Phase 1.3 diagnoses whether P3's `1 ATR` stop is frequently touched before the
same signal later reaches `+2 ATR`. It measures executable-side M5 MAE/MFE until
the session cutoff and does not select a new stop or strategy:

```bash
.venv/bin/python -m gbpusd_structure run-phase1-3
```

The frozen diagnostic contract is documented in
[`docs/TECHNICAL_PLAN_PHASE1_3.md`](docs/TECHNICAL_PLAN_PHASE1_3.md).
The completed audit is recorded in
[`docs/PHASE1_3_RESULTS.md`](docs/PHASE1_3_RESULTS.md), with official local
evidence under `artifacts/phase1_3/c9475ab43c8aba4a/`.
