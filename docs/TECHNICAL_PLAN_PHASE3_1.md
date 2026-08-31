# Technical Plan — Phase 3.1 Trend Second-Entry Outcomes

**Status:** preregistered before construction returns  
**Branch:** `phase/03-1-trend-second-entry-outcomes`  
**Parent coverage fingerprint:** `c29e50d70f87c916`

## 1. Research question

Phase 3.1 asks whether the only Phase-3 setup family with independent coverage,
`with_trend_second_entry`, has positive expectancy after the temporary Exness
Raw Spread execution model. It does not revise the price-action state machine,
signal thresholds, session caps, or setup selection.

This is a 2024 construction test. The same year helped define the research
program and is not a pristine holdout, so even a pass means “candidate for
external validation,” not a proven edge.

## 2. Frozen sample

The Phase-3 coverage artifact selected 164 chronological, triggered
`with_trend_second_entry` setups. They were frozen before outcomes were opened:

```text
parent fingerprint = c29e50d70f87c916
setup count        = 164
membership SHA-256 = 9fc2ef0753d36450bbde995d96bcd0f64209e2f90c3a31cb374fba5f69c39996
```

Membership is the sorted newline-delimited `setup_id` list. Phase 3.1 must
rebuild that list from the same causal definitions and match the count and hash
exactly. The two range families remain excluded because each produced only one
trigger; their outcome paths must not be inspected here.

The frozen session caps remain one London setup and two New York setups per
session opportunity.

## 3. Entry and protective stop

The stop-entry order already exists in Phase 3:

- long: buy when Ask trades at or above `signal Ask high + 0.10 pip`;
- short: sell when Bid trades at or below `signal Bid low - 0.10 pip`;
- validity: the next two M5 bars, bounded by the session cutoff; and
- a gap beyond the trigger fills at the worse executable open.

The video explicitly places the protective stop beyond the signal bar. This is
translated to executable quote sides:

```text
long stop  = signal-bar Bid low - 0.10 pip
short stop = signal-bar Ask high + 0.10 pip
```

The stop must be strictly beyond the entry reference. A wrong-side or missing
stop is an invariant failure, not a skipped or repaired trade.

Because M5 OHLC cannot reveal the path inside the trigger candle, any
entry/stop/target ambiguity in that candle is resolved conservatively with the
stop first. The number of such same-entry-bar exits is reported explicitly.

## 4. Target and session exit

The video describes taking a scalp and holding a runner but does not provide a
mechanical target or trailing rule. Phase 3.1 therefore tests one primary exit
only, based on the user's previously stated `1:2` preference:

```text
geometric risk = absolute(entry reference - signal-bar stop)
long target    = entry reference + 2 × geometric risk
short target   = entry reference - 2 × geometric risk
```

No `3R`, partial-exit, breakeven, or trailing variant is inspected in this
phase. If neither barrier resolves first, the trade exits at the last
executable quote at the registered London/New York management cutoff.

## 5. Costs and fixed-dollar reporting

The temporary broker model remains unchanged:

- existing HistData observed Bid/Ask path, not claimed as Exness history;
- commission `0.35 pip` per side;
- primary slippage `0.10 pip` per side;
- stress slippage `0.20 pip` per side;
- stop-first M5 intrabar priority; and
- no swap because every position is flat by the session cutoff.

Position size is reported for `$30` geometric risk:

```text
theoretical lots = 30 / (risk pips × 10 USD per pip per standard lot)
```

Lot quantization is disabled until the Exness MT5 feed and symbol constraints
are available. Costs can make a stopped trade lose more than `1R`; results are
not clipped.

## 6. Preregistered decision gate

The candidate advances only if all of the following hold in 2024:

- zero invariant failures and exact frozen membership;
- positive primary mean net R and profit factor above one;
- positive mean net R under stress slippage;
- positive primary expectancy in London and New York;
- positive primary expectancy for long and short trades;
- the day-cluster bootstrap 95% CI lower bound for mean trade R is above zero;
  and
- no single best month supplies more than 50% of total positive monthly R.

A pass only permits external broker-feed validation without retuning. A failure
stops the setup; it does not unlock post-hoc filters, alternative targets, or
2025 replication.

## 7. Required outputs and invariants

The runner writes primary and stress trades, scope/month/exit summaries,
bootstrap results, membership evidence, and a machine-readable gate decision.

Required invariants include:

- one simulated trade for every one of the 164 frozen setups;
- no range-family outcome access;
- order availability is no later than the trigger-bar open;
- quote-side trigger reproduction for every entry;
- stop and target on the correct side of entry;
- no bar after the registered cutoff;
- primary and stress runs use identical membership and raw price paths; and
- only the twelve 2024 canonical M5 files are opened.

Any invariant failure invalidates the performance result.
