# Phase 0 Results — Mechanical Definition Audit

**Status:** executed; baseline gate failed 9 of 65 checks  
**Dataset:** GBPUSD, 2024-01-01 through 2025-12-31  
**Run fingerprint:** `e8d6095e758c2792`  
**Trading/P&L:** intentionally absent

## Outcome

The implementation is causal and the core event chronology is generally stable,
but the registered baseline cannot advance unchanged. All point-in-time
invariants passed. The failures come from definitional quality and sample size,
not from profitable or unprofitable returns.

The one-pip near-equal rule classifies too many pivots as ambiguous, especially
on M15 and H1. Daily BOS/CHoCH and FVG also occur fewer than 30 times per year,
so Daily is not suitable as an event-trigger timeframe in this two-year sample.
H1 support/resistance activation is moderately sensitive to shrinking its
cluster tolerance from 0.20 to 0.10 ATR.

## Primary counts and quality

| Timeframe | Bars | Coverage >=95% | Swings | Ambiguous | Breaks | FVGs |
|---|---:|---:|---:|---:|---:|---:|
| M15 | 49,624 | 99.90% | 13,517 | 53.91% | 2,610 | 8,583 |
| H1 | 12,408 | 99.71% | 3,348 | 30.70% | 863 | 1,909 |
| H4 | 3,120 | 97.69% | 778 | 13.62% | 233 | 512 |
| Daily | 521 | 99.04% | 128 | 6.25% | 47 | 54 |

Support/resistance produced 1,028 H1 zones, of which 534 reached two confirmed
touches. H4 produced 281 zones, of which 142 became active.

## Failed gates

| Gate | Scope | Observed | Required |
|---|---|---:|---:|
| Ambiguous swings | M15 | 53.91% | <=5% |
| Ambiguous swings | H1 | 30.70% | <=5% |
| Ambiguous swings | H4 | 13.62% | <=5% |
| Ambiguous swings | Daily | 6.25% | <=5% |
| Annual event count | Daily breaks, 2024 | 21 | >=30 |
| Annual event count | Daily breaks, 2025 | 26 | >=30 |
| Annual event count | Daily FVG, 2024 | 25 | >=30 |
| Annual event count | Daily FVG, 2025 | 29 | >=30 |
| Sensitivity agreement | H1 S/R at 0.10 ATR | 64.47% | >=70% |

## What passed

- Zero look-ahead, duplicate-event, lifecycle, or OHLC invariant failures.
- Upstream aggregation coverage passed on M15, H1, H4, and Daily after applying
  the configured New York FX-week boundary.
- Swing right-window sensitivity passed on every timeframe.
- Break-buffer sensitivity passed on every timeframe.
- FVG minimum-size sensitivity passed on every timeframe.
- H4 S/R sensitivity passed; H1 passed at 0.30 ATR but failed at 0.10 ATR.
- M15, H1, and H4 comfortably exceeded the minimum annual event count for
  swings, breaks, and FVGs.

## Interpretation and next decision

This result does not say market structure has or lacks edge. Phase 0 never
measured forward return, win rate, or P&L. It says the current vocabulary is not
fully admissible as frozen:

1. Daily should remain a slow context/regime input, not a BOS/CHoCH or FVG entry
   trigger, until more years are available.
2. Ambiguous pivots must continue to be excluded from downstream state. Before
   Phase 1, the near-equal rule needs a preregistered refinement or an explicit
   waiver supported by a separate sensitivity audit; the 5% gate must not be
   silently relaxed after seeing this result.
3. H1 S/R should not be treated as a precise objective level. Its tolerance
   sensitivity supports testing it only as a contextual zone, with H4 as the
   more stable source.

Full generated evidence is gitignored under
`artifacts/phase0/e8d6095e758c2792/`, including aggregated bars, primary labels,
annual/monthly counts, sensitivity comparisons, `summary.json`, and the hashed
manifest.
