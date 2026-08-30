# Phase 1.5 Coverage Results — FVG Pullback Entry

**Status:** coverage frozen before construction P&L  
**Coverage fingerprint:** `033953375cc05c79`  
**Parent fingerprint:** `41fe02f5ef90868b`

## M1 data gate

The existing HistData tick archives produced 372,048 construction-year M1
bars. Re-aggregation reproduced all 74,876 canonical 2024 M5 bars with zero
membership, Bid/Ask/Mid OHLC, or tick-count mismatch.

## Entry coverage

| Variant | 2024 entries | Mean/month | Research minimum | Desired 20–25/month |
|---|---:|---:|---:|---:|
| E0 immediate parent | 384 | 32.00 | baseline | above range |
| E1 M5 FVG mitigation | 250 | 20.83 | pass | pass |
| E2 nested M1 FVG | 170 | 14.17 | pass | fail |

Both candidates exceed the preregistered 120-entry research minimum and are
therefore eligible for construction P&L. Only E1 satisfies the original
240–300 annual frequency objective. E2 remains evaluable but cannot be reported
as meeting the user's desired frequency.

## Funnel losses before entry

| Reason | E1 | E2 |
|---|---:|---:|
| Invalid parent structural mapping | 1 | 1 |
| No directional M5 FVG | 10 | 10 |
| No mitigation before cutoff | 18 | 18 |
| Stop reached before entry | 24 | 36 |
| Original target reached before entry | 82 | 90 |
| No nested M1 FVG before cutoff | — | 60 |
| Valid entry | 250 | 170 |

Target-before-entry is a cancelled opportunity, not a loss. It means the move
resolved before a pullback entry appeared. No later M15 signal replaces it.

All monthly, session, and direction cells remained populated. Coverage had zero
causality or output-schema invariant failures, and no return field was accessed
or written.

The eligible definitions and counts are frozen in
`config/phase1_5_coverage_selection.yaml` before construction returns are opened.

