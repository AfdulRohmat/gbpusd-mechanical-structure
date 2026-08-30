# Technical Plan — Phase 1 Nested Price Baselines

**Status:** preregistered before Phase-1 P&L inspection  
**Branch:** `phase/01-nested-price-baselines`  
**Purpose:** test simple price-only baselines before adding fundamentals or
secondary indicators

## 1. Research question

Does a causal GBPUSD market-structure signal add executable value beyond a
fixed session direction, simple H4 momentum, and mechanical H4 support or
resistance interaction after observed Bid/Ask spread, Exness Raw Spread
commission, and adverse slippage?

Phase 1 is not an attempt to optimize an SMC confluence score. It establishes a
small nested price-only ladder. Construction evidence is 2024 and historical
replication is 2025. No 2025 result may change a threshold or definition in
this document.

## 2. Frozen exclusions

- Order Blocks are excluded from signals, filters, entries, stops, targets, and
  reporting strata. Their Phase-0.2 geometry gate failed.
- H1 support/resistance is excluded because its registered stability score was
  69.69%, below 70%. Only H4 zones are admitted.
- Fundamentals, EMA, and RSI are excluded. They require later incremental
  phases after the price-only reference is known.
- Daily BOS, CHoCH, and FVG cannot trigger entries. Daily context is reported as
  a slow stratum only and cannot gate a Phase-1 trade.
- No parameter search, P&L-based threshold choice, stop/target grid, or
  session-specific strategy deletion is permitted.

## 3. Opportunity calendar

An opportunity is a valid weekday London or New York session with an observed
M5 bar beginning exactly at the civil session open. DST is resolved with the
registered IANA timezones. Each model may open at most one position per
session. A missing signal remains an explicit no-trade opportunity with return
zero; it is not removed from model comparisons.

London and New York signals may be observed during the first 90 minutes of
their respective sessions. London positions are flat by the New York open; New
York positions are flat by the 17:00 New York FX-day boundary.

## 4. Frozen baseline ladder

### P0 — session drift

At the session open, enter the fixed direction fitted separately for London and
New York on 2024. The fit compares an always-long with an always-short trade
under the primary full-cost simulator and chooses the higher mean net R. An
exact tie resolves to long. The selected direction is then frozen for 2025.
The 2024 P0 metric is descriptive because it contains this fit.

### P1 — H4 momentum

At the session open, use the two most recent fully available H4 closes. Enter
long when the latest close is above the prior close and short when below it. An
exact tie creates no trade. No structural or fundamental label is used.

### P2 — H4 support/resistance

Use only H4 zones that had at least two confirmed touches and were already
active before the candidate M15 setup bar began. The zone snapshot must be no
older than 500 completed H4 bars.

During the 90-minute observation window, the first qualifying M15 event is:

- resistance breakout: close above the upper bound plus `0.05 × M15 ATR`;
- support breakout: close below the lower bound minus that buffer;
- support rejection: the M15 range enters support and closes back above its
  upper bound; or
- resistance rejection: the range enters resistance and closes back below its
  lower bound.

Breakout direction follows the break; rejection direction points away from the
zone. If more than one zone qualifies on the same bar, sort by distance from
the prior M15 close normalized by ATR, then breakout before rejection, then
`zone_id`. The signal becomes available only when the M15 bar closes.

### P3 — M15 structure

Use the first causally available M15 BOS or CHoCH during the observation
window. Direction follows the break. Unclassified breaks, swings, FVGs, Daily
events, and wick-only probes do not trigger P3.

### P4 — top-down structure

P4 is a strict subset of P3. At the P3 decision timestamp, the latest available
H1 and H4 context states must both equal the signal direction: bullish for long
and bearish for short. Daily context remains a report-only stratum.

### P5 — top-down structure plus FVG

P5 is a strict subset of P4. The M15 break bar must qualify as displacement and
must create a registered same-direction M15 FVG on that same bar. The FVG is
known at the same completed-bar timestamp; entry remains on the following M5
bar. FVG age or later fill information is forbidden at the decision.

## 5. Entry and execution

- P0/P1 decide at the session open and enter at that M5 bar's observed open.
- P2–P5 enter on the first observed M5 open at or after the completed M15
  signal's `available_at` timestamp.
- Long enters Ask and exits Bid. Short enters Bid and exits Ask.
- The observed entry quote before slippage anchors the bracket.
- Primary adverse slippage is 0.10 pip per side; stress is 0.20 pip per side.
- Commission is USD 3.50 per standard lot per side, equivalent to 0.35 pip per
  side for GBPUSD under the registered USD 10 per pip convention.
- Spread is not added synthetically because it is already present in observed
  Bid/Ask quotes.

## 6. Risk and exit state machine

Signal-time M15 ATR defines `1R`. Stop distance is `1.0 ATR`; target distance is
`2.0 ATR`. The simulator checks executable-side M5 quotes. A gap through a stop
fills at the worse observed open; a favorable target gap receives no price
improvement. When stop and target are both reachable in one M5 bar, stop wins.
If neither is reached, the position exits at the final available M5 close no
later than the registered session cutoff. No trailing stop, partial exit,
overnight hold, or re-entry is allowed.

Net R includes quote spread, two-sided slippage, and round-trip commission. The
primary and stress simulations use the same signals and bracket levels so the
stress test changes execution assumptions only.

## 7. Causality invariants

- Every context, zone, break, and FVG must satisfy
  `available_at <= decision_at`.
- A P2 zone must additionally be active before the setup bar starts.
- The entry bar timestamp must be at or after the decision timestamp and before
  the management cutoff.
- P4/P5 trade IDs must be subsets of their registered parent model.
- No Order Block or H1 S/R field may appear in a Phase-1 signal record.
- Construction and replication rows are separated only by the frozen calendar
  boundary, never by random splitting.

Any invariant failure invalidates the run independently of P&L.

## 8. Reporting and uncertainty

Primary comparisons use a common session-day opportunity panel. A model without
a trade receives zero R for that opportunity. This reports both signal quality
and opportunity coverage. Per-trade expectancy, win rate, profit factor, total
R, target/stop/time exits, and trade frequency are secondary metrics.

Reports are split by year, session, direction, event type, and latest Daily
context. Confidence intervals use 10,000 deterministic bootstrap samples
clustered by FX session date so London and New York observations from the same
day are resampled together.

## 9. Frozen advancement gate

P0–P3 are reference baselines. Only P4 and P5 are advancement candidates. A
candidate advances only when all conditions hold:

1. zero causality or execution invariant failures;
2. at least 60 trades in each year;
3. at least 30 replication trades in each session and each direction;
4. positive construction and replication net expectancy;
5. positive replication expectancy independently in London, New York, long,
   and short strata;
6. replication profit factor above one;
7. the 95% day-cluster bootstrap lower bound for replication mean opportunity R
   is above zero;
8. replication expectancy remains positive at 0.20-pip-per-side slippage;
9. the best positive month contributes no more than 50% of all positive monthly
   R; and
10. replication mean opportunity R improves on the nearest parent: P4 over P3
    and P5 over P4.

Passing these gates means historical replication, not live readiness. Failure
is retained as evidence and cannot be repaired by changing Phase-1 thresholds
after inspecting the result.

## 10. Phase boundary

Phase 1 ends with the price-only baseline report. Fundamental alignment,
impact-weighted fundamental sensitivity, EMA/RSI ablations, alternate exits,
and Exness-specific MT5 replacement data remain separate future changes. The
next phase must start from these frozen Phase-1 signals or explicitly explain a
new preregistration.
