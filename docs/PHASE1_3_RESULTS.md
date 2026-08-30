# Phase 1.3 Results — MAE/MFE and Stop-Adequacy Audit

**Status:** completed; diagnostic evidence only  
**Fingerprint:** `c9475ab43c8aba4a`  
**Parent fingerprint:** `90d1e369b427d3d8`

## Outcome

The `1 ATR` stop is demonstrably premature for a material minority of P3
signals, but it is not the primary explanation for P3's negative result.

Of the paths classified stop-first under the original `1 ATR` stop and `+2 ATR`
target, 27.31% in construction and 23.28% in replication later reached the same
`+2 ATR` target before session cutoff. These are strict recoveries: the target
first appeared in a later M5 candle, not the stop candle.

At the same time, 178 stopped paths in each year never subsequently reached
`+2 ATR`. Most original stop-first paths therefore remained directional
failures within the registered session horizon.

All 768 frozen P3 signals were reproduced with zero invariant failures.

## Original `1 ATR` stop / `+2 ATR` destination

| Period | Signals | Target before stop | Stop first | Strict stop then target later | Strict premature / stop-first | Neither |
|---|---:|---:|---:|---:|---:|---:|
| 2024 construction | 385 | 80 | 249 | 68 | 27.31% | 56 |
| 2025 replication | 383 | 95 | 232 | 54 | 23.28% | 56 |

Three 2024 paths first exposed both thresholds in the same M5 candle. They are
retained as `same_bar_ambiguous_stop_first` and excluded from the strict
premature numerator. There were no such paths in 2025.

Measured against all P3 signals, strict premature stops represented 17.66% in
2024 and 14.10% in 2025. This is large enough that stop placement matters, but
not large enough to explain away the broader signal-quality problem.

The result also repeated across both sessions and directions rather than coming
from one isolated subgroup:

| Period | Scope | Value | Strict premature / stop-first |
|---|---|---|---:|
| 2024 | Session | London | 30.70% |
| 2024 | Session | New York | 24.44% |
| 2024 | Direction | Long | 27.73% |
| 2024 | Direction | Short | 26.92% |
| 2025 | Session | London | 20.20% |
| 2025 | Session | New York | 25.56% |
| 2025 | Direction | Long | 21.31% |
| 2025 | Direction | Short | 25.45% |

These strata are descriptive only and cannot be used as post-hoc filters.

## What wider stops recover at the same `+2 ATR` destination

| Stop | Effective reward:risk | 2024 target before stop | 2024 original premature saved | 2025 target before stop | 2025 original premature saved |
|---:|---:|---:|---:|---:|---:|
| 1.00 ATR | 2.00 | 80 | 0 / 68 | 95 | 0 / 54 |
| 1.25 ATR | 1.60 | 92 | 12 / 68 | 113 | 18 / 54 |
| 1.50 ATR | 1.33 | 105 | 25 / 68 | 122 | 27 / 54 |
| 2.00 ATR | 1.00 | 116 | 36 / 68 | 133 | 38 / 54 |

Wider stops do protect some paths that the original stop discarded. However,
holding the target at `+2 ATR` mechanically reduces reward relative to risk.
The table is therefore a path diagnosis, not evidence that a wider fixed stop
has positive expectancy after costs and time exits.

## What happens when `1:2` is preserved

Preserving `1:2` moves the target outward with the stop:

| Stop / target | 2024 target before stop | 2024 target share of resolved barriers | 2025 target before stop | 2025 target share of resolved barriers |
|---|---:|---:|---:|---:|
| 1.00 / 2.00 ATR | 80 | 24.32% | 95 | 29.05% |
| 1.25 / 2.50 ATR | 64 | 21.19% | 90 | 30.82% |
| 1.50 / 3.00 ATR | 64 | 23.36% | 81 | 30.11% |
| 2.00 / 4.00 ATR | 45 | 20.00% | 56 | 27.18% |

The shares exclude paths where neither barrier was reached and are not strategy
win rates. Even so, every value is below the frictionless 33.33% break-even
target share for a pure `1:2` bracket. Commission, slippage, and time exits have
not been applied in this diagnostic table. Widening the ATR stop while moving
the target proportionally therefore has no obvious support as a standalone
repair.

## Excursion distribution

| Period | Median MAE | Median MFE | 75th percentile MAE | 75th percentile MFE | Reached +2 ATR sometime |
|---|---:|---:|---:|---:|---:|
| 2024 | 1.83 ATR | 1.48 ATR | 3.68 ATR | 3.05 ATR | 39.22% |
| 2025 | 1.61 ATR | 1.49 ATR | 3.06 ATR | 3.09 ATR | 38.90% |

These are full paths through cutoff with the stop disabled. They show that
ordinary session movement frequently exceeds `1 ATR` on both sides of entry.
ATR alone consequently describes recent volatility but does not locate the
market-structure invalidation point.

## Decision

Phase 1.3 supports the narrow conclusion that stop geometry contributes to P3
underperformance. It rejects the stronger claim that the negative result is
mainly an artifact of the `1 ATR` stop.

No ATR multiplier is selected. If research continues, the next test should be a
separately preregistered comparison between:

1. the original `1 ATR` stop;
2. a causal structure-invalidation stop; and
3. a limited ATR/structure hybrid with fixed dollar risk through position
   sizing.

That test must include full spread, commission, slippage, time exits, and a
frozen construction-to-replication selection rule. It should not simultaneously
change signal frequency or add a `1:3` target.

Generated evidence is gitignored under
`artifacts/phase1_3/c9475ab43c8aba4a/`.

