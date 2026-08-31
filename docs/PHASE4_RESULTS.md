# Phase 4 Results — Structural Stop + Fixed `2 ATR` Management

## Decision

**Historical gate: failed.**

The completed-M5 `+1 signal ATR` breakeven protection reduced losses and
maximum drawdown relative to the static structural-stop baseline, but it did
not create positive full-cost expectancy. The paired improvement was small and
its session-date cluster-bootstrap interval crossed zero.

The preregistered action is therefore:

```text
close_structure_stop_2atr_management_repair
```

No trigger threshold, protected-stop level, session, direction, or month is
retuned after seeing this result.

## Evidence identity and boundary

- Branch: `phase/04-structure-stop-2atr-improvement`
- Preregistration commit: `6f2a7aa`
- Frozen simulator commit: `7fc75e1`
- Invariant-only correction commit: `4efaa78`
- Official artifact fingerprint: `714032a25c3b9f23`
- Parent signal fingerprint: `90d1e369b427d3d8`
- Evaluation: frozen 2025 P3 signals
- Signal count: 383/383
- Valid structural mappings: 383/383
- Invariant failures: 0
- Membership SHA-256:
  `d7bf7882c2cc08184d34c41b47ee91dd6b41cc8cc98494736f2fe148cfe2753a`

The 2025 period is historical replication, not a pristine program-wide
holdout. The Phase 4 candidate's 2024 return was not calculated; 2024 price
bars supplied causal structure warmup only. Execution still uses the temporary
HistData Bid/Ask proxy plus modeled Raw Spread commission and slippage, not
broker-specific Exness history.

### Implementation correction before the completed run

The first historical command calculated trades in memory but stopped before
writing or displaying results. An invariant checker had reduced the candidate
DataFrame to bracket-comparison columns and then reused that variable for an
activation-column check. The fix renamed the narrowed comparison frame and
added a regression test. It did not change signals, state transitions, fills,
costs, thresholds, or gates. The empty failed-run directory has no evidence
files; the completed fingerprint above is the sole official run.

## Overall result

Primary friction is `0.10 pip/side` slippage plus `0.35 pip/side` commission.
Dollar values use the registered constant `$30` geometric risk per trade.

| Variant | Trades | WR | Mean net R | Total net R | PF | Max DD | Fixed-risk P&L |
|---|---:|---:|---:|---:|---:|---:|---:|
| Static structural stop | 383 | 51.44% | -0.0411 | -15.76 | 0.876 | 28.90R | -$472.76 |
| `+1 ATR` then breakeven | 383 | 36.03% | -0.0267 | -10.22 | 0.886 | 18.04R | -$306.65 |

Under `0.20 pip/side` stress slippage, candidate expectancy fell to
`-0.0353R/trade`, total return to `-13.52R`, profit factor to `0.852`, and
maximum drawdown rose to `20.66R`.

The candidate's average positive trade was `+0.575R` and its average negative
trade was `-0.365R`, producing a `1.57` realized payoff ratio. That payoff
requires approximately `38.87%` winners to break even, while the observed win
rate was `36.03%`.

The static baseline illustrates why win rate alone is not an edge: it won
`51.44%` of trades but its average win was only `+0.566R` versus an average
loss of `-0.684R`.

## Session and direction stability

| Candidate scope | Trades | Mean net R | PF | Max DD |
|---|---:|---:|---:|---:|
| London | 173 | -0.0374 | 0.836 | 11.66R |
| New York | 210 | -0.0178 | 0.925 | 12.11R |
| Long | 204 | -0.0471 | 0.809 | 17.01R |
| Short | 179 | -0.0035 | 0.984 | 6.63R |

Neither session was positive. Short trades came close to flat under primary
friction, but became `-0.0118R/trade` under stress and were not a registered
standalone candidate. Selecting them now would be post-hoc subgroup mining.

Only five of twelve candidate months were positive. The best month supplied
`30.73%` of total positive monthly R, which passed the registered 50% monthly
concentration limit but did not offset the failed expectancy conditions.

## What the protection state changed

The candidate observed the `+1 ATR` trigger in 230 trades and activated
protection on the next M5 bar in 227. Of all 383 paired trades, 120 changed
outcome and 263 were unchanged.

| Baseline path affected | Trades | Candidate minus baseline |
|---|---:|---:|
| Eventual structural-stop exits | 31 | +30.88R |
| Eventual target exits | 40 | -28.13R |
| Eventual session-cutoff exits | 49 | +2.78R |
| **Net paired change** | **120** | **+5.54R** |

The protection did its intended mechanical job: it converted 31 future full
stops and 49 later time exits into much smaller losses. But 40 paths that first
reached `+1 ATR`, retraced, and later reached the fixed target were also cut.
Those sacrificed continuations consumed almost all of the saved stop risk.

Candidate exit composition was:

- 101 target exits;
- 120 protected-stop exits, including six gaps;
- 60 structural-stop exits, including one gap; and
- 102 session-cutoff exits.

Before modeled commission and slippage, but still using the observed Bid/Ask
path, the candidate averaged only `+0.0121R/trade`. Modeled friction averaged
`0.0388R/trade`, leaving the full-cost result at `-0.0267R/trade`. The raw edge
was therefore too small to trade through the registered execution model.

## Paired uncertainty and gate

The paired candidate-minus-baseline improvement was:

```text
estimate             +0.01446 R/trade
95% cluster CI       -0.02644 to +0.05421 R/trade
session-date clusters 242
bootstrap resamples   10,000
```

Passed checks:

- exact parent membership;
- zero invariant failures;
- positive point estimate versus baseline;
- lower maximum drawdown; and
- monthly concentration within limit.

Failed checks:

- positive primary expectancy;
- profit factor above one;
- paired CI lower bound above zero;
- positive stress expectancy;
- positive expectancy in both sessions; and
- positive expectancy in both directions.

## Interpretation

Phase 4 found a useful risk-shaping effect, not a strategy edge. The management
rule exchanged target participation for loss compression and improved the
equity-path shape, but it could not repair a weak underlying signal/bracket.

The 2025 static baseline was less negative than the 2024 Phase 1.4 diagnostic
(`-0.041R` versus `-0.147R/trade`), yet both periods remained below zero after
costs. Combined with the Phase 2 finding that the underlying structure
directions lacked robust gross forward-return information, the evidence does
not support another threshold sweep on this same P3 setup.

## Reproduction

```bash
.venv/bin/python -m gbpusd_structure run-phase4-historical
```

The official local, gitignored evidence is under:

```text
artifacts/phase4/historical/714032a25c3b9f23/
```

The directory contains frozen membership, structural mappings, primary and
stress trades, scope metrics, paired differences, monthly and exit summaries,
bootstrap evidence, manifest, and the machine-readable gate decision.
