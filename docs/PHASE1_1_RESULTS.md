# Phase 1.1 Results — Full-Session Setup Revision

**Status:** executed; no advancement candidate passed  
**Dataset:** GBPUSD, 2024-01-01 through 2025-12-31  
**Official run fingerprint:** `90d1e369b427d3d8`  
**Engine commit:** `f3b2fb1`  
**Parent fingerprint:** `daac4b3ee86ac545`

## Outcome

The full-session revision implemented the intended opportunity process. P2–P5
could select their first complete valid setup at any time from London open to
New York open or from New York open to the FX-day cutoff. P4 and P5 continued
searching after an earlier structural event failed their complete filter.

Coverage increased materially, but no model met the frozen evidence gates. The
run had zero causality, session-assignment, parent-baseline, or execution
invariant failures. P0 and P1 signals were identical to the parent run.

## Opening-window versus full-session coverage

| Model | Parent 90-minute window | Full session | Added |
|---|---:|---:|---:|
| P0 session drift | 1,038 | 1,038 | 0 |
| P1 H4 momentum | 1,034 | 1,034 | 0 |
| P2 H4 S/R | 624 | 810 | 186 |
| P3 M15 structure | 323 | 768 | 445 |
| P4 H1+H4-aligned structure | 9 | 49 | 40 |
| P5 aligned displacement/FVG | 0 | 4 | 4 |

The revised engine enumerated 1,286 causal M15 BOS/CHoCH candidates across the
full sessions. Of these, 246 aligned with H1, 310 aligned with H4, and 58 aligned
with both. Four of the jointly aligned candidates also had displacement and a
same-bar, same-direction FVG.

Joint alignment occurred on 21 candidates in 2024 and 37 in 2025. Because a
session can contain more than one qualifying candidate, the first-valid-per-
model selection produced 19 P4 trades in 2024 and 30 in 2025.

## Full-session replication performance

| Model | Trades | Win rate | Mean R/trade | Profit factor | Total R | Mean R/opportunity |
|---|---:|---:|---:|---:|---:|---:|
| P0 session drift | 518 | 30.12% | -0.231 | 0.708 | -119.799 | -0.2313 |
| P1 H4 momentum | 516 | 30.23% | -0.222 | 0.718 | -114.584 | -0.2212 |
| P2 H4 S/R | 419 | 34.84% | -0.106 | 0.854 | -44.206 | -0.0853 |
| P3 M15 structure | 383 | 34.20% | -0.160 | 0.767 | -61.399 | -0.1185 |
| P4 top-down structure | 30 | 40.00% | +0.058 | 1.094 | +1.746 | +0.0034 |
| P5 plus displacement/FVG | 2 | 50.00% | +0.409 | 1.759 | +0.818 | +0.0016 |

P3's replication opportunity-mean 95% day-cluster interval was
`[-0.2143R, -0.0239R]`, entirely below zero. Full-session coverage therefore
made the negative P3 result stronger, not weaker.

P4's replication interval was `[-0.0183R, +0.0272R]` per opportunity. Its
positive point estimate was not statistically resolved and did not replicate
the construction period.

## P4 stability diagnosis

P4 failed chronologically:

| Period | Trades | Mean R/trade | Win rate | Profit factor | Total R |
|---|---:|---:|---:|---:|---:|
| 2024 construction | 19 | -0.201 | 31.58% | 0.685 | -3.828 |
| 2025 replication | 30 | +0.058 | 40.00% | 1.094 | +1.746 |

It also failed the registered cross-session requirement in replication:

| Session | Trades | Mean R/trade | Profit factor |
|---|---:|---:|---:|
| London | 14 | +0.455 | 1.929 |
| New York | 16 | -0.289 | 0.603 |

Long produced `+0.002R/trade` across 18 observations and short
`+0.142R/trade` across 12. Neither direction met the 30-trade minimum. At the
registered 0.20-pip-per-side stress slippage, overall P4 replication fell to
`+0.036R/trade` but remained positive.

The London and BOS strata looked better after the run, while New York and CHoCH
were negative. Those are diagnostics only. Selecting London-only or BOS-only
now would be an unregistered post-hoc strategy and is not used to rescue P4.

## Effect of expanding the setup window

- P3 replication increased from 165 to 383 trades. Mean trade return improved
  from `-0.222R` to `-0.160R`, but the larger participation increased total loss
  from `-36.55R` to `-61.40R` and made mean opportunity return more negative.
- P4 replication increased from six to 30 trades. Its unstable six-trade mean
  of `+0.881R` contracted to `+0.058R`, while construction remained negative.
- P5 became observable only four times across both years: two construction
  losses and two replication trades. It remains unusably sparse.

The 90-minute opening window was therefore one cause of the earlier low count,
but not the primary reason the candidate failed. Exact joint alignment still
represented only 4.51% of full-session structural candidates, and the expanded
sample did not establish chronological or cross-session profitability.

## Advancement decision

- P4: **fail** — insufficient year/session/direction counts, negative
  construction expectancy, negative New York replication, and replication CI
  crossing zero.
- P5: **fail** — four total trades, negative construction, concentration
  failure, and no incremental improvement over P4.
- Phase-1.1 advancement: **none**.

Order Blocks, H1 support/resistance, fundamentals, EMA, RSI, and Daily entry
triggers were not used. No session hour, event subtype, alignment definition,
stop, target, or cutoff is changed after inspecting the result.

Generated evidence is gitignored under
`artifacts/phase1_1/90d1e369b427d3d8/`, including all M15 candidates, selected
signals, primary and stress trades, local-hour counts, parent comparison,
common opportunity panels, bootstrap intervals, `summary.json`, and the hashed
manifest.
