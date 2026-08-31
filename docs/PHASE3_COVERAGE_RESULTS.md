# Phase 3 Coverage Results — Price-Action State Machine

**Status:** definition and coverage gate passed; P&L remains unopened  
**Coverage fingerprint:** `c29e50d70f87c916`  
**Construction year:** 2024 only  
**Invariant failures:** zero

## Outcome

The rules extracted from the supplied price-action video can be represented as
a causal M15/M5 state machine. It classified 99.86% of eligible in-session M15
bars and produced 166 chronologically selected stop-entry triggers in 2024,
approximately `13.83` per month.

The mandatory research-coverage gate passed, but the user's desired frequency
of 20–40 triggers per month did not. No return, stop, target, trade result, win
rate, profit factor, or P&L was calculated.

The practical result is narrower than “the video strategy works”:

- `with_trend_second_entry` has enough coverage for a separately frozen P&L
  construction test;
- failed-range-break fade and accepted-breakout pullback do not have enough
  coverage under the preregistered definitions; and
- Phase 3 currently behaves overwhelmingly as a trend-lifecycle model rather
  than a balanced trend/range router.

## M15 state coverage

There were 13,941 in-session M15 snapshots:

| State group | Bars | Share |
|---|---:|---:|
| Active up/down trend | 5,321 | 38.17% |
| Trendline break pending final extreme | 5,859 | 42.03% |
| Post-extreme transition | 2,583 | 18.53% |
| Range and breakout lifecycle | 158 | 1.13% |
| Undetermined | 20 | 0.14% |

The high classified fraction is real but should not be confused with balanced
regime discovery. Trend and trend-transition states account for 98.72% of
in-session bars. This follows from the frozen priority rule: an already proven
trend remains controlling until its trendline/final-extreme lifecycle resolves
or an opposite HH/HL–LH/LL trend is proven. A rolling range cannot override an
active trend merely because recent price is sideways.

Key transitions occurred frequently enough to confirm that the machine is not
stuck in one state:

| Transition | Count |
|---|---:|
| Uptrendline close break | 803 |
| Downtrendline close break | 718 |
| Up final extreme fulfilled | 455 |
| Down final extreme fulfilled | 370 |
| Opposite trend overrode pending extreme | 696 |
| Same-direction trend reproven | 801 |
| Post-extreme range confirmed | 23 |

The range lifecycle generated 35 initial buffered breaks, 28 two-close
acceptances, 17 accepted breakout-retest holds, and 7 failed-break re-entries.

## M5 setup funnel

| Family | Raw candidates | Eligible signals | Selected | Triggered |
|---|---:|---:|---:|---:|
| With-trend second entry | 1,321 | 227 | 207 | 164 |
| Failed-range-break fade | 1 | 1 | 1 | 1 |
| Accepted-breakout pullback | 1 | 1 | 1 | 1 |
| **Total** | **1,323** | **229** | **209** | **166** |

For the trend family, 554 candidates passed signal-bar quality, 520 intersected
at least one EMA21/projected-trendline key-entry zone, and 43 were identified as
congestion. The joint rule admitted 227; chronological London/New York caps
retained 207, of which 164 triggered within the next two M5 bars.

The range state machine emitted 24 M15 context events, but only two found a
qualifying M5 signal at the frozen boundary within the registered three-bar
wait. This is a structural coverage failure for the range families, not
permission to widen the signal window after seeing the funnel.

## Frequency distribution

Selected triggers were balanced by direction and present in every month:

| Scope | Trigger count |
|---|---:|
| Long | 85 |
| Short | 81 |
| London | 55 |
| New York | 111 |

Monthly trigger counts ranged from 8 to 17. Total mean frequency was 13.83 per
month. The New York allowance of two setups per session explains part of the
session difference; this table is coverage, not performance.

## Gate decision

Passed:

- zero causal/membership invariant failures;
- at least 60% classified M15 bars;
- at least 120 selected signals;
- at least 120 triggered signals;
- trigger rate above 50% (`79.43%` observed);
- at least 30 triggers in London and New York; and
- at least 30 long and short triggers.

Not achieved:

- desired frequency of 240–480 triggers/year: `166` observed.

The preregistered minimum gate permits a construction P&L stage. Before that
stage, the return-blind selection must freeze only
`with_trend_second_entry`; the two range families have one trigger each and are
not statistically evaluable.

## Interpretation boundary

Phase 3 establishes that the video's sequential logic can be made explicit and
causal. It does not establish predictive edge. In particular:

- the visually subjective trendline was replaced by the last two confirmed
  opposing pivots;
- “close enough” final extremes use a fixed `0.10 ATR` tolerance;
- “good signal bar” uses body, close-location, and normalized-range thresholds;
- EMA21 is location support only; and
- no claim that most range breakouts fail was assumed or validated.

The valid runner opened only the twelve 2024 M5 files. Phase-3 2025 data and all
outcome fields remained closed.

Generated evidence is gitignored under
`artifacts/phase3/coverage/c29e50d70f87c916/`.
