# Phase 1.5 Results — FVG Pullback Entry

**Status:** stopped after construction; replication remained locked  
**Coverage fingerprint:** `033953375cc05c79`  
**Construction fingerprint:** `80e415a3f056942d`  
**Structural parent fingerprint:** `41fe02f5ef90868b`

## Outcome

M5 FVG mitigation successfully improved median entry location and nearly restored
a `1:1` median reward:risk while preserving the parent's structural stop and
absolute target. It did not improve conditional expectancy. Waiting for the
pullback excluded many strong continuation moves, reduced win rate, and left
both candidates negative after complete costs.

Neither construction candidate qualified. No winner file was created and no
2025 FVG-entry return was calculated. Coverage and construction each completed
with zero invariant failures.

## Audited data and coverage

The local HistData tick archives generated 372,048 construction M1 bars. They
reconciled exactly to all 74,876 canonical M5 bars across Bid/Ask/Mid OHLC and
tick count.

| Variant | Entries | Mean/month | Desired 20–25/month |
|---|---:|---:|---:|
| E0 immediate structural parent | 384 | 32.00 | above range |
| E1 M5 FVG mitigation | 250 | 20.83 | pass |
| E2 nested M1 FVG refinement | 170 | 14.17 | fail |

E1 achieved the intended frequency. E2 passed the 120-entry research minimum
but did not satisfy the user's frequency objective.

## Construction performance

| Variant | Trades | Win rate | Mean R/trade | Profit factor | Total R | Mean R/opportunity |
|---|---:|---:|---:|---:|---:|---:|
| E0 immediate parent | 384 | 45.05% | -0.147 | 0.616 | -56.525 | -0.1087 |
| E1 M5 FVG mitigation | 250 | 41.20% | -0.166 | 0.586 | -41.514 | -0.0798 |
| E2 nested M1 FVG | 170 | 41.18% | -0.155 | 0.561 | -26.299 | -0.0506 |

Both candidates improved mean return per common session opportunity only because
they traded less. They failed positive mean trade return and profit factor above
one. Stress slippage reduced E1 to `-0.179R/trade` and E2 to
`-0.166R/trade`.

## Did FVG improve entry location?

Yes for E1, but not enough to improve the selected trade population:

| Diagnostic | E0 | E1 M5 mitigation | E2 nested M1 |
|---|---:|---:|---:|
| Median risk distance | 21.57 pip | 19.26 pip | 20.22 pip |
| Median target R before costs | 0.697R | 0.988R | 0.795R |
| Median favorable entry improvement | — | 3.10 pip | 1.35 pip |
| Entries better than immediate | — | 193 / 250 | 113 / 170 |
| Entries worse than immediate | — | 56 / 250 | 54 / 170 |
| Target R at least 1R | — | 48.80% | 34.71% |
| Target R at least 2R | — | 10.00% | 4.12% |

E1 did what its geometry intended: most entries were better and median payoff
rose materially. E2 waited for a new nested M1 imbalance after mitigation. By
the time that confirmation completed, much of the pullback advantage had been
given back; its median target R fell below E1.

## Selection effect

The pullback requirement did not merely improve the same 384 trades. It selected
a different subset:

- E1 cancelled 82 setups because the original target was reached before entry.
- E2 cancelled 90 for the same reason.
- E1 also cancelled 24 setups at structural invalidation before entry; E2
  cancelled 36.

The target-before-entry group contains fast directional continuations that an
immediate strategy could capture but a retracement strategy necessarily misses.
After removing many of those moves, E1 win rate declined from 45.05% to 41.20%
despite its better entry price.

Exit counts reinforce the point:

| Variant | Target | Stop | Session cutoff |
|---|---:|---:|---:|
| E0 | 133 | 104 | 147 |
| E1 | 57 | 70 | 123 |
| E2 | 38 | 38 | 94 |

## Construction strata

Every registered E1 and E2 session/direction scope remained negative. E1 long
was the least negative at `-0.063R/trade` with profit factor `0.825`, while E1
short was `-0.272R/trade` with profit factor `0.385`. These values were observed
after the run and cannot authorize a long-only filter.

## Decision

Phase 1.5 rejects both preregistered FVG entry mechanisms as positive-expectancy
repairs for P3:

- E1 met frequency and improved entry geometry, but worsened mean trade return.
- E2 added latency, missed the frequency objective, and remained negative.
- Qualified construction candidates: **none**.
- 2025 M1 build for strategy replication: **not required**.
- 2025 FVG-entry returns: **not opened**.

This result does not mean every discretionary FVG entry is ineffective. It means
the first causal post-signal M5 FVG mitigation and the frozen nested-M1 rule did
not add edge to this P3 signal under the current data and cost model.

Generated evidence is gitignored under:

- `artifacts/phase1_5/coverage/033953375cc05c79/`; and
- `artifacts/phase1_5/construction/80e415a3f056942d/`.

