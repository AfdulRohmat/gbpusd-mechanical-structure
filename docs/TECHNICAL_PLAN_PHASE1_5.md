# Technical Plan — Phase 1.5 FVG Pullback Entry

**Status:** preregistered before coverage and return results  
**Branch:** `phase/01-5-fvg-pullback-entry`  
**Signal parent:** Phase 1.1 fingerprint `90d1e369b427d3d8`  
**Structural parent:** Phase 1.4 construction fingerprint `41fe02f5ef90868b`

## 1. Research question

Phase 1.4 raised construction win rate from 27.53% to 45.05% when the original
`+2 signal ATR` destination was paired with structural invalidation. It remained
negative because median structural risk was `2.87 signal ATR`, leaving median
pre-cost reward:risk near `0.697:1`.

Phase 1.5 asks whether waiting for a lower-timeframe Fair Value Gap pullback can
improve entry location while preserving the same M15 signal, absolute
destination, structural invalidation, session cutoff, and full costs.

EMA and RSI are excluded. Adding them in the same phase would prevent attribution
of any improvement to entry geometry.

## 2. Frozen parent geometry

Each opportunity begins with the frozen first M15 BOS/CHoCH P3 signal. Its
structural stop is reconstructed with the Phase 1.4 rule. A mapping that is
missing or on the wrong side of the eventual entry is non-tradable and reported;
it is never repaired with an entry-relative floor.

The absolute target is frozen from the original immediate entry:

```text
long destination  = parent immediate Ask entry + 2 signal ATR
short destination = parent immediate Bid entry - 2 signal ATR
```

The target does not move when a pullback produces a better entry. This isolates
entry location and allows reward relative to structural risk to improve.

## 3. Lower-timeframe FVG definition

Both M5 and M1 use the same causal three-candle wick-gap definition:

```text
bullish FVG: third mid low > first mid high
bearish FVG: third mid high < first mid low
```

Gap size must be at least `0.10` of the third bar's completed 14-period simple
true-range ATR. The three bars must be contiguous. A gap becomes available only
when the third bar closes.

Only gaps matching the parent signal direction are eligible. The first eligible
M5 FVG available at or after the M15 decision is frozen for that signal; the
engine may not skip an unhelpful first gap for a later one.

## 4. Entry variants

### E0 — immediate parent entry

Reproduce Phase 1.4's structural-stop / fixed-`2 ATR` diagnostic baseline.

### E1 — M5 FVG mitigation

After the first directional M5 FVG becomes available, wait for a strictly later
M5 candle to touch its proximal boundary. Stop and target checks have priority
over mitigation. If neither has resolved the setup, enter at the next M5 open.

The delayed entry must remain between structural stop and target and occur before
session cutoff. There is no rejection-close requirement and no 50%/consequent-
encroachment tuning.

### E2 — M5 FVG plus M1 refinement

After the parent M5 FVG is first mitigated, wait for the first same-direction M1
FVG whose zone overlaps the parent M5 FVG zone. It must form after mitigation
and becomes available only after its third M1 candle closes. Enter at the next
M1 open.

M1 FVGs outside a mitigated M5 zone are ignored. This keeps M1 as execution
refinement rather than an independent high-frequency signal generator.

## 5. Pre-entry cancellation

Every completed bar before entry is evaluated in fixed order:

1. structural stop touched;
2. frozen absolute target touched;
3. FVG mitigation or refinement trigger.

Stop wins when stop and target occur in the same bar. A setup is also cancelled
if no entry exists before cutoff or the eventual entry lies beyond stop/target.
No cancelled signal can be replaced by a second M15 signal in that session.

## 6. M1 data contract

M1 Bid/Ask bars are streamed from the existing monthly HistData tick ZIPs; no
new download is required. Source time is fixed EST (`Etc/GMT+5`) and converted
to UTC exactly as in the M5 producer.

M1 output must be unique, UTC-aware, OHLC-valid, and reconcile to canonical M5
for Bid/Ask/Mid OHLC and tick counts. Derived monthly Parquet is gitignored under
the shared data root. Failure to reconcile invalidates E2.

## 7. Staged evidence lock

### Stage A — 2024 coverage only

Stage A may inspect timestamps, price geometry, and cancellation state but may
not calculate, join, or emit return, exit-P&L, win, profit-factor, or expectancy
fields.

A candidate needs at least 120 construction entries (10/month) to receive P&L.
The original frequency objective of 240–300 entries (20–25/month) is reported
separately and is not silently relaxed. This lower research minimum permits a
nested entry mechanism to be diagnosed without claiming it met the desired
trading frequency.

Coverage eligibility and counts must be committed before construction returns
are opened.

### Stage B — 2024 construction P&L

Only coverage-eligible candidates are simulated. A candidate qualifies only if
it has zero invariants, positive mean full-cost R, profit factor above one, and
higher mean R per common session opportunity than E0. At most one winner can be
frozen for historical replication.

If no candidate qualifies, 2025 FVG-entry returns remain unopened.

## 8. Execution and risk

- Long entry uses Ask; short entry uses Bid.
- Long exits on Bid; short exits on Ask.
- Primary and stress slippage remain `0.10` and `0.20` pip per side.
- Round-trip commission remains `0.70 pip`.
- Stop-first resolution and session force-close remain frozen.
- R is normalized by the new entry-to-structural-stop distance.
- Theoretical lot size preserves `$30` geometric risk without lot rounding.

## 9. Invariants

- E0 reproduces the valid Phase 1.4 parent trades.
- Every FVG uses three contiguous completed bars and is available before use.
- E1 mitigation occurs after M5 FVG availability.
- E2 refinement occurs after M5 mitigation and overlaps the parent zone.
- No entry occurs before its decision or at/after cutoff.
- Every entry remains on the valid side of stop and target.
- At most one entry exists per session.
- Coverage artifacts contain no return or P&L fields.
- Construction artifacts contain no 2025 FVG-entry returns.

Any invariant failure invalidates the stage regardless of coverage or returns.
