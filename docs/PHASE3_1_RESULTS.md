# Phase 3.1 Results — Trend Second-Entry Outcomes

**Status:** stopped after construction; no replication or external validation  
**Construction fingerprint:** `883fbf40556a866f`  
**Parent coverage fingerprint:** `c29e50d70f87c916`  
**Frozen setup membership:** 164 / exact hash match  
**Invariant failures:** zero

## Outcome

The preregistered `with_trend_second_entry` signal-bar-stop/`2R` bracket failed
the 2024 construction gate. After observed Bid/Ask spread, `0.35 pip` commission
per side, and `0.10 pip` slippage per side, it produced:

| Trades | Win rate | Mean net R | Total net R | Profit factor | Maximum drawdown |
|---:|---:|---:|---:|---:|---:|
| 164 | 25.61% | -0.446R | -73.07R | 0.455 | 79.30R |

At the theoretical `$30` fixed geometric risk used for position-size
normalization, total return was approximately `-$2,191.96`. This is not a
historical account-equity claim because lot quantization and actual Exness
history remain unavailable.

The result is valid for the exact registered bracket. It does not establish
that all price-action exit models fail, and it does not validate the video's
unquantified performance claims.

## Execution result

| Exit | Count | Share |
|---|---:|---:|
| Signal-bar stop after the entry bar | 101 | 61.59% |
| Conservative stop on the entry bar | 11 | 6.71% |
| `2R` target after the entry bar | 28 | 17.07% |
| `2R` target on the entry bar | 1 | 0.61% |
| Session cutoff | 23 | 14.02% |

There were 112 stop-first paths versus 29 target-first paths. Among resolved
brackets, the target-first share was only 20.57%, well below the frictionless
33.33% required by a pure `1:2` payoff.

The 11 conservative entry-bar stops are not the cause of the decision. Even an
impossible best-case reassignment of all 11 from `-1R` stops to `+2R` targets
would improve the result by only about `33R`, leaving the strategy near
`-40R` after costs.

## Gross signal versus execution costs

The bracket was already negative before modeled slippage and commission:

| Component | Mean per trade | Total |
|---|---:|---:|
| Gross bracket outcome | -0.284R | -46.64R |
| Modeled cost drag | -0.161R | -26.43R |
| Net outcome | -0.446R | -73.07R |

The median signal-bar risk was only `5.7 pips` (`2.4` minimum; `26.4` maximum),
so the fixed `0.9 pip` round-trip slippage-plus-commission assumption consumed a
median `0.158R`. Costs materially amplified the loss, but removing them would
not make the frozen bracket positive.

Stress slippage of `0.20 pip` per side reduced the result further to `-78.94R`,
mean `-0.481R`, and profit factor `0.430`.

## Registered robustness checks

The setup was negative in every registered session and direction:

| Scope | Trades | Win rate | Mean net R | Total net R | Profit factor |
|---|---:|---:|---:|---:|---:|
| London | 54 | 29.63% | -0.244R | -13.20R | 0.664 |
| New York | 110 | 23.64% | -0.544R | -59.86R | 0.367 |
| Long | 84 | 23.81% | -0.519R | -43.59R | 0.397 |
| Short | 80 | 27.50% | -0.368R | -29.47R | 0.521 |

Only January and October finished positive. The best month supplied 69.79% of
all positive monthly R, above the registered 50% concentration ceiling.

The session-date cluster bootstrap 95% interval for mean trade R was
`[-0.623R, -0.260R]`. It is entirely below zero rather than merely failing to
clear zero.

## Post-hoc path diagnosis: stop geometry matters

After the registered result was known, the full paths were observed through the
same session cutoff without terminating measurement at the first bracket exit.
This diagnostic cannot qualify or rescue a strategy.

| Full-path sequence | Count |
|---|---:|
| Stop touched; `+2R` never reached | 74 |
| Stop touched; `+2R` reached later | 38 |
| `+2R` reached without stop | 26 |
| `+2R` reached before a later stop | 3 |
| Neither threshold reached | 23 |

Of the 112 stop-first paths, 38 (33.93%) later reached `+2R`. The signal-bar
stop therefore discarded a material number of eventual favorable moves. But 74
stopped paths still never reached the target, so widening or removing the stop
is not automatically a solution.

As a deliberately post-hoc reference, marking every frozen entry only at the
session cutoff—without a stop or target—would have produced mean `+0.184R`,
total `+30.25R`, 46.34% positive trades, and profit factor `1.181` after the same
cost assumption. London, New York, long, and short means were all positive.

That counterfactual is not evidence of a deployable edge:

- it was inspected only after the registered bracket failed;
- its median was still `-0.227R`, so the positive mean depended on a right tail;
- its day-cluster 95% interval was `[-0.341R, +0.756R]`, which includes zero;
- it has no hard catastrophic-risk rule; and
- 2024 is already a heavily inspected construction year.

The valid inference is only that exit geometry, especially truncating long-tail
moves with a tight signal-bar stop, deserves separate forward-frozen research.

## Gate decision

Passed:

- zero invariant failures; and
- exact 164-setup parent membership and hash.

Failed:

- positive primary expectancy;
- profit factor above one;
- positive stress expectancy;
- positive expectancy in both sessions;
- positive expectancy in both directions;
- positive day-cluster CI lower bound; and
- monthly concentration limit.

The registered action is `stop_without_replication`. Phase 3.1 does not open
2025, does not promote the setup to Exness validation, and does not authorize a
post-hoc target, stop, trailing, or subgroup adjustment.

If research continues, the only defensible successor is a newly preregistered
exit thesis evaluated on data not used for this diagnosis—preferably the Exness
MT5 export or genuinely forward data. The rejected signal-bar-stop/`2R` bracket
must not be retuned on 2024.

Generated evidence is gitignored under
`artifacts/phase3_1/construction/883fbf40556a866f/`.
