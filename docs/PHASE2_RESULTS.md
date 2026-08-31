# Phase 2 Results — Directional Signal Edge Audit

**Status:** completed; current structure-signal thesis closed  
**Valid construction fingerprint:** `1fdb1a270eae74f6`  
**Construction period:** 2024 only  
**Invariant failures:** zero

## Outcome

None of the four preregistered M15 primitives demonstrated gross directional
edge. At the primary 60-minute horizon, BOS, CHoCH, displacement, and liquidity
sweep all had negative mean signed return. Every cluster-bootstrap confidence
interval crossed zero, every `1 ATR` favorable-first rate was below 50%, and no
primitive was consistent across session, direction, and horizon gates.

This audit deliberately excluded spread, commission, slippage, stop placement,
target selection, and position sizing. The failure therefore occurs before
execution friction: the current event direction itself does not predict the
next movement reliably enough to justify another FVG, Order Block, EMA, RSI,
or stop/target repair within this signal lineage.

## Primary sample and 60-minute result

The primary sample retained only the first event of each primitive in each
London or New York session. The small differences between event and evaluable
counts come from exact fixed-horizon M5 availability near data boundaries.

| Primitive | Primary events | Evaluable at 60m | Mean signed return | Positive return | Cluster-bootstrap 95% CI |
|---|---:|---:|---:|---:|---:|
| BOS continuation | 262 | 260 | -0.192 ATR | 44.23% | [-0.512, 0.108] |
| CHoCH reversal | 244 | 243 | -0.072 ATR | 48.97% | [-0.327, 0.167] |
| Displacement continuation | 518 | 518 | -0.095 ATR | 49.81% | [-0.320, 0.123] |
| Liquidity-sweep reversal | 386 | 386 | -0.002 ATR | 49.22% | [-0.203, 0.204] |

Liquidity sweep was closest to flat, not closest to demonstrated edge. Its mean
was approximately zero, its confidence interval was symmetric around zero, and
its positive-return rate was below 50%.

The diagnostic all-event sample led to the same interpretation at 60 minutes:
BOS `-0.111 ATR`, CHoCH `-0.081 ATR`, displacement `-0.034 ATR`, and sweep
`+0.009 ATR`. Repeated events therefore did not reveal a hidden effect that the
first-event sample removed.

## Horizon persistence

| Primitive | 15m | 30m | 60m primary | 120m | 240m | Positive horizons |
|---|---:|---:|---:|---:|---:|---:|
| BOS | -0.092 | -0.238 | -0.192 | +0.015 | -0.284 | 1 / 5 |
| CHoCH | -0.082 | +0.015 | -0.072 | -0.228 | +0.060 | 2 / 5 |
| Displacement | -0.058 | -0.015 | -0.095 | -0.300 | -0.116 | 0 / 5 |
| Liquidity sweep | +0.026 | +0.046 | -0.002 | +0.100 | -0.087 | 3 / 5 |

All values are gross signed returns normalized by the event's frozen M15 ATR.
The isolated positive cells had confidence intervals crossing zero. No
primitive reached the registered requirement of four positive horizons.

## `+1 ATR` versus `-1 ATR` first touch

The barrier diagnostic observes up to 240 minutes and excludes same-bar
ambiguities and unresolved paths from the rate denominator.

| Primitive | Favorable first | Adverse first | Resolved favorable rate |
|---|---:|---:|---:|
| BOS | 110 | 126 | 46.61% |
| CHoCH | 112 | 117 | 48.91% |
| Displacement | 246 | 266 | 48.05% |
| Liquidity sweep | 176 | 191 | 47.96% |

Every value is below the preregistered 50% requirement. This agrees with the
fixed-horizon returns rather than pointing to a stop/exit artifact.

## Session and direction instability

No primitive was positive in both sessions and both directions at 60 minutes:

| Primitive | London | New York | Long | Short |
|---|---:|---:|---:|---:|
| BOS | -0.063 | -0.276 | -0.489 | +0.134 |
| CHoCH | -0.250 | +0.042 | +0.003 | -0.144 |
| Displacement | +0.151 | -0.339 | -0.208 | +0.019 |
| Liquidity sweep | +0.094 | -0.075 | -0.048 | +0.053 |

These opposing signs are descriptive diagnostics, not permission to select a
London-only, New-York-only, long-only, or short-only rule after seeing 2024.

H1/H4 alignment also could not repair the result. Most events fell into the
strict state machine's undetermined context, while the fully aligned scopes had
only 3–19 observations per primitive—far below the registered minimum of 30.

## Comparison with simple baselines

At the same 60-minute event timestamps, session mean reversion was positive for
all four samples:

| Event timestamp sample | Session momentum | Session mean reversion | Mean-reversion 95% CI |
|---|---:|---:|---:|
| BOS timestamps | -0.184 | +0.184 | [-0.114, 0.510] |
| CHoCH timestamps | -0.079 | +0.079 | [-0.157, 0.328] |
| Displacement timestamps | -0.131 | +0.131 | [-0.084, 0.352] |
| Sweep timestamps | -0.098 | +0.098 | [-0.100, 0.302] |

Every confidence interval still crossed zero. Session mean reversion is
therefore an interesting separately preregistered hypothesis, not a qualified
strategy from Phase 2.

On timestamps where the four-bar close breakout emitted a direction, it was
negative for every primitive sample. For BOS, its direction exactly matched
the event on the 231 paired observations and produced `-0.266 ATR`; renaming a
simple close breakout as BOS did not add information.

All event-direction means also remained below their registered 97.5th-percentile
random-direction null thresholds.

## Gate decision

All primitives passed only coverage and zero-invariant checks. None passed:

- positive primary 60-minute mean;
- cluster-bootstrap lower bound above zero;
- performance above the random-null upper threshold;
- favorable-first rate above 50%;
- positive London, New York, long, and short scopes;
- four positive registered horizons; or
- positive paired improvement over both session momentum and mean reversion.

Qualified primitives: **none**.  
Recommended winner: **none**.  
Phase-2 historical replication permitted: **no**.

The registered action is to close the current BOS/CHoCH/sweep/displacement
directional thesis. This does not prove that every discretionary interpretation
called SMC is impossible. It does show that the repo's mechanical definitions
have no measurable gross directional advantage in 2024, so further entry and
indicator layering would be post-hoc complexity without a supported parent
signal.

## Evidence boundary and audit trail

The valid runner opened only the twelve canonical M5 files for 2024. It did not
calculate Phase-2 forward returns for 2025. Nevertheless, 2025 is not a pristine
program-wide holdout because prior phases already reported P3 outcomes for that
year.

An earlier implementation run (`6378ff754faee3f3`) was invalidated by an entry
anchor assertion before its performance output was interpreted. The correction
and unchanged preregistered contract are documented in
[`PHASE2_IMPLEMENTATION_NOTES.md`](PHASE2_IMPLEMENTATION_NOTES.md).

Generated valid evidence is gitignored under
`artifacts/phase2/construction/1fdb1a270eae74f6/`.
