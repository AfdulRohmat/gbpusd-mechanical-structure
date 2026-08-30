# Phase 0.2 Results — Order Block Definition Audit

**Status:** executed; 30 of 33 registered gates passed
**Dataset:** GBPUSD, 2024-01-01 through 2025-12-31
**Run fingerprint:** `1a35c7d3d407a3e4`
**Trading/P&L:** intentionally absent

## Outcome

Order Block formation is mechanically observable, causal, frequent enough, and
stable to changes in candidate lookback and lifecycle age. However, the price
zone itself is not stable to a basic geometry choice. Full-wick and body-range
zones failed the preregistered 50% median interval-overlap gate on M15, H1, and
H4.

Because an Order Block's boundary would directly determine touch, entry, and
stop placement, stable event timestamps are not sufficient. Order Blocks are
therefore recorded as `strategy_admitted: false` and are excluded from Phase 1.
No threshold was changed after the audit.

## Formation evidence

| Timeframe | Eligible anchors | Candidate found | Created OB | 2024 | 2025 |
|---|---:|---:|---:|---:|---:|
| M15 | 1,210 | 99.17% | 1,199 | 567 | 632 |
| H1 | 343 | 98.83% | 339 | 165 | 174 |
| H4 | 86 | 97.67% | 82 | 36 | 46 |

Only 16 anchors lacked an opposing candle inside the frozen six-bar window.
Three additional anchors selected a candidate already activated by an earlier
break and were deterministically rejected as duplicates.

Median candidate distance was two bars on every timeframe; the 95th percentile
was four bars. All annual frequency gates passed.

## Lifecycle evidence

| Timeframe | Fully mitigated | Invalidated | Expired | Active at sample end |
|---|---:|---:|---:|---:|
| M15 | 370 | 428 | 401 | 0 |
| H1 | 104 | 116 | 118 | 1 |
| H4 | 28 | 24 | 30 | 0 |

Lifecycle sensitivity at 25 and 100 bars passed on all timeframes, with
agreement ranging from 74.47% to 81.67%. Candidate-lookback sensitivity at 3
and 9 bars also passed, ranging from 85.37% to 99.41%.

Same-displacement FVG confluence occurred on 19.02% of M15, 20.94% of H1, and
15.85% of H4 Order Blocks. FVG confluence was diagnostic only and was not
required for formation.

## Failed geometry gates

| Timeframe | Full-wick vs body median IoU | Required |
|---|---:|---:|
| M15 | 42.86% | >=50% |
| H1 | 37.00% | >=50% |
| H4 | 44.05% | >=50% |

These are three independent failures of the same underlying issue: the answer
to “where exactly is the Order Block?” changes materially when a common body
versus wick convention changes. The result is not a data-quality, sample-size,
or point-in-time failure. All causality and lifecycle invariants passed.

## Disposition before Phase 1

- Order Block labels remain available for research diagnostics.
- Order Blocks cannot be used as entry zones, filters, confluence, stops, or
  targets in the Phase-1 baseline.
- The Phase-1 admissible set remains causal swing relationships, protected-swing
  BOS/CHoCH, M15/H1/H4 FVG, Daily context, and H4 support/resistance.
- H1 support/resistance remains excluded by the separate Phase-0.1 decision.

Full generated evidence is gitignored under
`artifacts/phase0_2/1a35c7d3d407a3e4/`, including Order Block zones, anchor audit
rows, sensitivity comparisons, `summary.json`, and the hashed manifest.
