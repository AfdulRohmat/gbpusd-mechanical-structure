# Research Closure — GBPUSD Mechanical Structure

**Status:** closed  
**Closed on:** 2026-09-01  
**Final verdict:** no deployable edge found

## Decision

This repository is closed as a completed negative research program. None of the
preregistered mechanical GBPUSD candidates demonstrated positive, robust,
full-cost expectancy with sufficient sample support.

No strategy from this repository is approved for live or forward deployment.
The code and evidence remain an audit archive; they are not a production
trading system.

## What was learned

The project successfully converted discretionary-sounding concepts into causal,
testable definitions. It also showed why several visually convincing ideas did
not survive mechanical execution:

- BOS and CHoCH labels can be generated point in time, but their registered
  direction did not predict forward GBPUSD movement reliably.
- Strict H1/H4 alignment reduced the sample too aggressively and did not
  replicate across years and sessions.
- The original `1 ATR` stop was premature on a meaningful minority of paths,
  but stop placement was not the primary source of negative expectancy.
- Structural invalidation reduced loss severity, while its wider risk distance
  made either the payoff or target reachability unattractive.
- M5/M1 FVG pullbacks improved entry geometry but systematically missed fast
  continuation winners.
- Breakeven protection reduced drawdown but sacrificed enough eventual target
  winners to leave the strategy negative after costs.
- Win rate was not a sufficient quality measure. A 51.44% baseline still lost
  because its realized payoff distribution was unfavorable.

## Evidence path

| Study | Main result | Decision |
|---|---|---|
| Phase 0/0.1 | Causal structure vocabulary established; H1 S/R sensitivity remained below its strict gate | Retain labels, exclude unstable H1 S/R trigger |
| Phase 0.2 | Order Block geometry failed M15, H1, and H4 convention-overlap gates | OB diagnostic only |
| Phase 1 | Nested price candidates failed; sampled P3 replication was `-0.222R/trade` | No advancement |
| Phase 1.1 | Full-session P3 reached 383 trades in 2025 but returned `-0.160R/trade` | Frequency was not the root problem |
| Phase 1.2 | Displacement and context-veto filters reached desired frequency but remained negative | No filter selected |
| Phase 1.3 | 23.28% of 2025 stop-first paths later reached `+2 ATR` | Stop geometry mattered but did not explain the missing edge |
| Phase 1.4 | 2024 structure stop + fixed `2 ATR` reached 45.05% WR but returned `-0.147R/trade` | No structural-stop candidate selected |
| Phase 1.5 | FVG entries improved price geometry but returned between `-0.155R` and `-0.166R/trade` | FVG repair rejected |
| Phase 2 | BOS, CHoCH, displacement, and sweep had no robust gross directional advantage | Underlying signal thesis closed |
| Phase 4 | 2025 breakeven management reduced DD from 28.90R to 18.04R but remained `-0.0267R/trade`, PF `0.886` | Management repair closed |

Every official result and its evidence boundary is recorded in the corresponding
`PHASE*_RESULTS.md` document. Generated parquet/CSV evidence remains local and
gitignored under `artifacts/`.

## Why the research stops here

The final Phase 4 candidate improved its static baseline by
`+0.01446R/trade`, but the paired 95% interval was
`[-0.02644R, +0.05421R]` and absolute expectancy remained negative. Before
modeled commission and slippage, its observed-Bid/Ask path had only
`+0.0121R/trade`; registered friction averaged `0.0388R/trade`.

Another sweep of ATR triggers, session subsets, directions, BOS/CHoCH types,
hours, EMA/RSI values, or FVG variants would now select parameters from known
outcomes. That would increase overfitting risk without a supported parent
signal. Losing less is useful diagnosis, but it is not evidence of an edge.

## Claims this closure does not make

This result does **not** prove that:

- every discretionary price-action or SMC method is impossible;
- GBPUSD or forex CFD trading cannot be profitable;
- fundamentals, EMA, or RSI have been disproven; or
- the temporary HistData execution proxy exactly represents Exness Raw Spread.

Those broader claims were outside the completed tests. Fundamentals and
EMA/RSI were deliberately not layered onto a parent price signal that had
already failed its gross directional audit.

The supported conclusion is narrower: the exact causal structure, FVG, stop,
target, and management rules tested here did not produce a deployable GBPUSD
edge on the available 2024–2025 data under the registered cost model.

## Archive state

- `main` is the intended final research record.
- Phase branches remain preserved and are not deleted.
- No winner file, live parameter set, or deployment recommendation exists.
- Historical artifacts remain reproducible when the shared data path is
  available.
- Reopening this signal lineage for post-hoc threshold tuning is explicitly
  outside the closed research decision.

Any future study would need a genuinely new causal hypothesis, a new
preregistration, account-aligned execution data, and evidence not used to design
that hypothesis. It should not be presented as a rescue of this repository.
