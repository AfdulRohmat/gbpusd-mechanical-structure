# Phase 1 Results — Nested Price Baselines

**Status:** executed; no advancement candidate passed  
**Dataset:** GBPUSD, 2024-01-01 through 2025-12-31  
**Official run fingerprint:** `daac4b3ee86ac545`  
**Engine commit:** `bb6b7be`  
**Price source:** temporary HistData Bid/Ask development proxy

## Outcome

Phase 1 found no robust price-only edge under the preregistered `1 ATR` stop,
`2R` target, session cutoff, and full-cost execution model.

The run had zero causality or execution invariant failures. Order Blocks, H1
support/resistance, fundamentals, EMA, and RSI were not used. The negative
result is therefore a test of the frozen Phase-1 price baselines, not of those
deferred components.

There were 1,038 valid session-day opportunities: 520 in 2024 construction and
518 in 2025 replication.

## Signal funnel

| Model | 2024 | 2025 | Total |
|---|---:|---:|---:|
| P0 fitted session drift | 520 | 518 | 1,038 |
| P1 latest completed H4 momentum | 518 | 516 | 1,034 |
| P2 first causal H4 S/R interaction | 301 | 323 | 624 |
| P3 first M15 BOS/CHoCH | 158 | 165 | 323 |
| P4 P3 aligned with H1 and H4 state | 3 | 6 | 9 |
| P5 P4 plus displacement and same-bar FVG | 0 | 0 | 0 |

P0 fitted short for London and long for New York on construction. This did not
hide a profitable construction direction: all four session/direction choices
were negative before selection. The selected London and New York construction
means were `-0.317R` and `-0.188R` per trade.

## Replication performance

| Model | Trades | Win rate | Mean R/trade | Profit factor | Total R | Mean R/opportunity |
|---|---:|---:|---:|---:|---:|---:|
| P0 session drift | 518 | 30.12% | -0.231 | 0.708 | -119.799 | -0.2313 |
| P1 H4 momentum | 516 | 30.23% | -0.222 | 0.718 | -114.584 | -0.2212 |
| P2 H4 S/R | 323 | 33.44% | -0.120 | 0.839 | -38.730 | -0.0748 |
| P3 M15 structure | 165 | 29.70% | -0.222 | 0.716 | -36.548 | -0.0706 |
| P4 top-down structure | 6 | 66.67% | +0.881 | 3.358 | +5.285 | +0.0102 |
| P5 plus displacement/FVG | 0 | — | — | — | 0.000 | 0.0000 |

The 2025 opportunity-mean 95% day-cluster intervals were entirely negative for
P0 and P1. They crossed zero for P2, P3, and P4. P4's interval was
`[-0.0043R, +0.0269R]` per session opportunity.

At the registered stress slippage of 0.20 pip per side, P2 produced
`-0.147R/trade`, P3 `-0.247R/trade`, and P4 `+0.854R/trade`. The P4 stress result
does not overcome its sample-size and non-replication failures.

## Why the top-down funnel collapsed

Among the 323 P3 signals:

- 57 were individually aligned with H1;
- 75 were individually aligned with H4; and
- only 9 were simultaneously aligned with both.

The most common P3 context pair was H1 `transition` plus H4 `transition` with
102 observations. Another 59 had H1 `transition` plus H4 `bullish`, and 42 had
H1 `transition` plus H4 `bearish`. Exact directional agreement across both
context state machines is therefore rare under the frozen Phase-0 definitions.

P4 is not evidence of an edge despite its positive 2025 point estimate. It had
only three construction trades, all losses, followed by six replication trades.
It failed the registered per-year, per-session, per-direction, construction
expectancy, and confidence-interval gates. P5 had no observations because none
of the nine P4 signals also met the same-bar displacement/FVG rule.

## Baseline diagnostics

Every P2 event subtype remained negative in replication:

| H4 S/R event | Trades | Mean R/trade | Profit factor |
|---|---:|---:|---:|
| Resistance breakout | 97 | -0.066 | 0.908 |
| Resistance rejection | 77 | -0.266 | 0.669 |
| Support breakout | 83 | -0.106 | 0.857 |
| Support rejection | 66 | -0.047 | 0.935 |

Within P3, CHoCH was less negative than BOS in 2025 (`-0.080R` versus
`-0.433R` per trade), but this is a reported post-run stratum, not a newly
validated strategy. Bullish, bearish, and transition Daily strata were all
negative for P3 replication.

## Advancement decision

- P4: **fail**. Positive six-trade replication is statistically and
  chronologically unsupported; construction was negative.
- P5: **fail**. Zero trades means the hypothesis is not observable at the
  registered session frequency.
- Phase-1 advancement: **none**.

No threshold, context requirement, S/R rule, stop, or target is changed after
seeing these results. Loosening H1/H4 alignment or removing the FVG requirement
would be a new preregistered experiment, not a rescue of Phase 1.

If a later phase tests point-in-time fundamentals, P3 is the adequately sampled
price-only comparison. P4/P5 cannot be treated as validated parents, and the
six positive replication trades must not be used to select a fundamental rule.

Generated evidence is gitignored under
`artifacts/phase1/daac4b3ee86ac545/`, including opportunities, signals, primary
and stress trades, common opportunity panels, metrics, bootstrap intervals,
the P0 fit, `summary.json`, and the hashed manifest.
