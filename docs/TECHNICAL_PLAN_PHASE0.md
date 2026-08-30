# Technical Plan — Phase 0 Mechanical Definition Audit

**Status:** Baseline executed; see `PHASE0_RESULTS.md`; no trading and no P&L
**Purpose:** establish causal labels before constructing a strategy

## 1. Objective

Phase 0 converts visual trading language into timestamped, testable objects. It
measures coverage, stability, frequency, confirmation delay, and definitional
sensitivity without using returns to select parameters.

No entry, stop, target, win rate, or expectancy is generated in this phase.

## 2. Inputs

- Canonical UTC GBPUSD M5 Bid/Ask bars from the existing 2024–2025 HistData
  dataset as a temporary development proxy.
- FX-day boundary at 17:00 America/New_York.
- Deterministically aggregated M15, H1, H4, and Daily bars.
- Point-in-time fundamental event tables are validated for later phases but do
  not affect structure labels in Phase 0.

Higher timeframes must be built from the same canonical M5 dataset. Broker chart
defaults are not assumed to share the required FX-day anchor.

The observed HistData Bid/Ask spread is retained rather than overwritten by an
invented constant Exness spread. It is a conservative execution proxy, not an
account-specific quote history. Future trading phases add the frozen Exness Raw
Spread commission and slippage from `config/execution.yaml`. Replacing the price
feed later must not alter any Phase-0 structural definition.

## 3. Initial operational definitions

### Swings

- Pivot window: two completed bars on each side.
- Equal-price tolerance: one pip.
- `pivot_at` identifies the candidate bar.
- `available_at` is the close of the second right-hand bar.
- Until `available_at`, the pivot must not appear in any downstream state.

### Structural regime

- A directional regime requires a confirmed sequence of higher highs/higher
  lows or lower highs/lower lows.
- A close beyond the active swing by at least `0.05 ATR` is a break candidate.
- A displacement-qualified break additionally requires candle body at least
  `0.80 ATR`.
- BOS continues the established direction.
- CHoCH is the first opposing break through the protected swing.
- Without an established directional regime, a break is `unclassified_break`,
  not CHoCH.

### Fair value gap

- Bullish: third-candle low is above first-candle high.
- Bearish: third-candle high is below first-candle low.
- Minimum gap: `0.10 ATR`.
- Availability: close of the third candle.
- Maximum tracking age: 24 bars.
- Full traversal of the gap invalidates it; partial fill is recorded separately.

### Support/resistance

- Source timeframes: H4 and H1.
- Inputs: confirmed swing prices only.
- Clustering tolerance: `0.20 ATR` at the zone's source timeframe.
- Minimum touches: two, each observable when its swing confirms.
- Maximum age: 500 source bars.
- A zone snapshot freezes at each decision timestamp; later touches cannot
  retroactively widen it.

### Deferred order block

Order-block labeling remains disabled. Before activation it requires a separate
document specifying candidate candle selection, displacement relationship,
zone bounds, mitigation, invalidation, overlap, and tie handling.

## 4. Registered sensitivities

Sensitivities are label-stability checks, not searches for profitable settings:

- swing right bars: 1, 2, and 3;
- break buffer: 0, 0.05, and 0.10 ATR;
- FVG minimum: 0, 0.10, and 0.20 ATR; and
- S/R cluster tolerance: 0.10, 0.20, and 0.30 ATR.

The frozen primary values remain those in `config/structure.yaml`. Sensitivity
results may determine whether a concept is too unstable to proceed, but no value
is selected using future returns.

## 5. Outputs

For every timeframe and year:

- bar coverage and aggregation integrity;
- label counts and events per month;
- candidate-to-confirmation delay;
- overlaps and ambiguous labels;
- BOS/CHoCH transition matrices;
- FVG size, age, partial-fill, full-fill, and expiry distributions;
- S/R zone count, width, touch count, age, and merge/split diagnostics; and
- agreement rates between primary and sensitivity definitions.

Each label table contains at least:

```text
symbol
timeframe
event_type
event_at
available_at
direction
source_bar_ids
definition_version
```

## 6. Phase gate

A concept can enter strategy construction only if:

- no point-in-time invariant fails;
- at least 95% of eligible periods have valid upstream bars;
- ambiguous classifications are below 5%;
- counts are sufficient for year/session reporting; and
- modest definition sensitivities preserve the broad event chronology rather
  than creating an unrelated label set.

Passing Phase 0 means only that the vocabulary is measurable. It does not mean
the concept predicts returns or has economic value.
