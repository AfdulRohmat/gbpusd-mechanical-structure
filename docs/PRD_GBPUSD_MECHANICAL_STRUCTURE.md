# PRD — GBPUSD Fundamental and Mechanical Market Structure Research

## 1. Purpose

Determine whether mechanically defined top-down structure, optionally conditioned
by point-in-time relative GBP/USD fundamentals, produces a robust and executable
GBPUSD edge after broker-realistic costs.

The project is independent from the auction/value/volume repository. Reusable
data engineering and statistical controls may be ported, but earlier negative
results do not validate or invalidate this strategy family.

## 2. Research question

Can a causal sequence of higher-timeframe context, confirmed structural level,
lower-timeframe trigger, and explicit execution rule outperform simpler
price-only baselines across time and market regimes?

The project does not ask whether a discretionary SMC chart can be explained
after the move. It asks whether every decision could have been produced in real
time by deterministic code.

## 3. Scope

- Instrument: GBPUSD CFD.
- Broker/execution reference: Exness Raw Spread on MT5.
- Context timeframes: Daily, H4, and H1.
- Setup timeframe: M15.
- Execution timeframe: M5, with Bid/Ask ticks when required.
- Trading windows: London and New York sessions.
- Fundamental layer: point-in-time relative GBP-minus-USD context.
- Structural candidates: swings, S/R zones, BOS, CHoCH, displacement, and FVG.
- Optional registered indicators: EMA and RSI.

Order blocks are out of the initial scope because their common definitions allow
substantial discretionary selection. They may enter only through a separate
pre-registered label study.

## 4. Non-goals

- Reproducing visual annotations from a trading educator.
- Maximizing in-sample win rate.
- Combining every available concept into one confluence score.
- Treating a renamed price pattern as independent evidence.
- Using future-confirmed swing points before their confirmation bar closes.
- Claiming live readiness from historical backtests.

## 5. Research principles

### Point-in-time availability

Every feature carries `observed_at` and `available_at`. A feature may affect a
decision only when `available_at <= decision_timestamp`. A swing requiring two
right-hand bars is unavailable until those two bars close.

### Baseline-first comparison

Every complex model must be compared with nested baselines:

1. unconditional session direction;
2. higher-timeframe momentum only;
3. mechanical S/R breakout or rejection;
4. market-structure trigger;
5. structure plus fundamental context; and
6. registered EMA/RSI ablations.

### Costs and executable quotes

Bid/Ask spread, Raw Spread commission, adverse slippage, gaps, and stop-first
intrabar ambiguity are included. Mid-price results may be diagnostic only.

### Multiple-testing discipline

Concepts are added one at a time. A component survives only when its incremental
effect replicates out of construction evidence. Thresholds are never changed in
response to validation P&L.

## 6. Evidence roles

- 2024: construction and label diagnostics.
- 2025: historical replication.
- January–July 2026: secondary out-of-time check, but not called untouched
  because it is accessible to the preceding research project.
- September 2026 onward: prospective lockbox after definitions and code freeze.

The absence of enough prospective months is reported as insufficient evidence,
not silently replaced by more tuning on older data.

## 7. Candidate structure vocabulary

### Confirmed swing

A pivot high/low with fixed left and right bar counts. The pivot timestamp and
availability timestamp are distinct.

### Break of structure

A completed close through the active confirmed swing in the established trend
direction, beyond a registered ATR-scaled buffer. Wick-only probes are tracked
separately.

### Change of character

The first confirmed close through the protected counter-trend swing after a
directional structure has been established. A CHoCH cannot exist in an
unclassified regime.

### Fair value gap

A three-candle wick gap that becomes known only after the third candle closes.
Gap fill, age, invalidation, and overlap with an entry are explicit.

### Support/resistance zone

A causal cluster of confirmed swing prices on registered timeframes. Zone width
is ATR-scaled and freezes between registered recomputation timestamps.

## 8. Fundamental role

Fundamentals are a context/filter, never a standalone entry. The primary score
uses equal weights across policy, inflation, labor, and yield expectations. The
previous impact-weighted scheme is retained only as a registered sensitivity.

The system tests whether structure performs differently when aligned, opposed,
or neutral relative to the point-in-time fundamental bias. It does not assume
alignment is beneficial.

## 9. Success criteria

A candidate edge must:

- remain positive after full execution costs;
- improve over its nearest simpler baseline;
- replicate across years and both sessions or have a pre-specified session
  scope;
- show enough trades for stable inference;
- avoid dependence on one month, one direction, or one news cluster;
- survive modest execution and definition perturbations; and
- remain frozen through a prospective period.

Exact numerical gates belong to the strategy-phase technical plan and must be
committed before its P&L is inspected.

## 10. Deliverables

- deterministic multi-timeframe bar construction;
- point-in-time swing/SR/BOS/CHoCH/FVG label engine;
- label audit and transition statistics;
- nested baseline strategy specifications;
- cost-aware event/trade simulator;
- year/session/regime reports with uncertainty intervals; and
- a final README conclusion including negative results.
