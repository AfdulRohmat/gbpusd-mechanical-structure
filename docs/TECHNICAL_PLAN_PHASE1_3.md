# Technical Plan — Phase 1.3 MAE/MFE and Stop-Adequacy Audit

**Status:** preregistered before path results  
**Branch:** `phase/01-3-stop-adequacy-audit`  
**Parent evidence:** Phase 1.1 fingerprint `90d1e369b427d3d8`

## 1. Research question

Phase 1.3 asks whether P3's fixed `1 ATR` stop frequently closes a position
before the same frozen signal subsequently reaches its original `+2 ATR`
destination within the same session. It separates signal-direction failure from
stop-placement failure.

This is a diagnostic audit, not a new strategy backtest. It cannot select a
profitable multiplier, change P3 signals, add filters, or promote a model.

## 2. Frozen sample

- Use only the frozen Phase 1.1 `p3_m15_structure` signals.
- Preserve the first M15 BOS/CHoCH per London or New York session.
- Report construction 2024 and historical replication 2025 separately.
- Observe every signal from its executable M5 entry bar until its existing
  session cutoff.
- Do not stop the counterfactual path when a threshold is touched.

The audit therefore measures what price did after the simulated strategy would
have exited, without creating a second entry or using future data to construct
the original signal.

## 3. Executable-side excursion definition

The entry anchor is unchanged from Phase 1.1 and excludes explicit slippage:

- long: Ask open at the first observed M5 bar at or after decision time;
- short: Bid open at that bar.

The path uses the quote side on which a position can be closed:

- long favorable/adverse excursion uses Bid high/low;
- short favorable/adverse excursion uses Ask low/high.

Observed spread is consequently present in MAE/MFE. Commission and modeled
slippage are excluded so that the audit diagnoses price-stop geometry rather
than mixing it with account sizing or transaction-cost P&L.

Excursions are normalized by the signal's frozen M15 ATR:

```text
long MAE = max(entry Ask - future Bid low) / ATR
long MFE = max(future Bid high - entry Ask) / ATR

short MAE = max(future Ask high - entry Bid) / ATR
short MFE = max(entry Bid - future Ask low) / ATR
```

## 4. Preregistered threshold paths

Stop thresholds are `1.00`, `1.25`, `1.50`, and `2.00 ATR`. Each is evaluated
against two target definitions:

1. fixed destination: the original `+2 ATR` target; and
2. RR-preserving destination: `2 × stop distance`.

Each signal/threshold pair receives exactly one sequence label:

- `target_before_stop`;
- `stop_then_target_later`;
- `stop_without_later_target`;
- `same_bar_ambiguous_stop_first`; or
- `neither_touched`.

`stop_then_target_later` requires the target to first occur in a strictly later
M5 bar. If both thresholds first appear in the same M5 candle, the order is not
observable and remains a separate ambiguity category. It retains the parent's
conservative stop-first interpretation but is not counted as proven premature.

The primary diagnostic is:

```text
strict premature-stop rate =
    1 ATR stop_then_target_later at fixed +2 ATR
    -------------------------------------------------
    all 1 ATR stop-first paths at fixed +2 ATR
```

The denominator includes strict premature, stop-without-later-target, and
same-bar stop-first paths.

## 5. Reports and interpretation

The audit writes signal-level excursion and threshold-path tables plus summaries
for overall, session, and direction scopes. It reports MAE/MFE quantiles, touch
rates, sequence counts, and strict premature-stop rates independently for 2024
and 2025.

Interpretation is constrained as follows:

- a high and repeated strict premature-stop rate supports revisiting stop
  geometry;
- a low rate indicates that widening the stop is unlikely to repair the P3
  directional signal;
- a wider stop reaching a farther RR-preserving target is not assumed merely
  because it preserves the original `1:2` ratio;
- no subgroup or multiplier may be selected as a new strategy from this audit.

Any subsequent stop ablation must be preregistered after reviewing this audit.
Dollar risk would remain fixed through position sizing; Phase 1.3 does not
simulate lot size.

## 6. Invariants

- Parent P3 signal and primary-trade counts match one-to-one.
- Entry timestamps and reference prices reproduce Phase 1.1.
- Every measured M5 bar is at or after decision time and before cutoff.
- Every signal has positive ATR and non-negative normalized MAE/MFE.
- The original `1 ATR`/`2 ATR` sequence agrees with the parent's stop/target
  touch outcome.
- Construction and replication outputs remain explicitly separated.

An invariant failure invalidates the audit regardless of the descriptive result.
