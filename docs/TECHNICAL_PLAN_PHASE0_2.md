# Technical Plan — Phase 0.2 Order Block Definition Audit

**Status:** preregistered before audit and executed; see `PHASE0_2_RESULTS.md`
**Purpose:** convert Order Block terminology into causal, testable zones without P&L

## 1. Scope

Phase 0.2 determines whether one deliberately minimal Order Block definition is
mechanically usable. It does not test entries, stops, targets, win rate, forward
return, or profitability.

Order Blocks are evaluated on M15, H1, and H4. Daily remains `regime_only` and
cannot create an entry-trigger-eligible Order Block.

## 2. Formation rule

An anchor is eligible only when all of the following are true:

- the event is a point-in-time `bos` or `choch`;
- the break is displacement-qualified by the existing `0.80 ATR` body rule;
- the event is not an `unclassified_break`; and
- the source timeframe is M15, H1, or H4.

For an upward anchor, the candidate is the most recent completed bearish candle
(`close < open`) before the displacement bar. For a downward anchor, it is the
most recent completed bullish candle (`close > open`). Doji candles are ignored.
The primary search window is the preceding six source bars. A candidate outside
that window is not used.

The candidate candle must itself pass the upstream structure-eligibility rule.
The displacement candle can never select itself. If no candidate exists, the
anchor is recorded as `no_opposing_candle`; no Order Block is invented.

## 3. Zone and availability

- Primary geometry is the candidate candle's complete mid-price wick range:
  `[mid_low, mid_high]`.
- Direction is inherited from the anchor break, not the candidate candle.
- `candidate_at` is the historical candle timestamp.
- `event_at` is the anchor break timestamp.
- `available_at` is the close of the displacement/break candle.
- The zone cannot be touched or mitigated before `available_at`.
- FVG overlap is recorded as confluence but is not required for formation.

A candidate candle can activate at most one Order Block per direction and
timeframe. The first qualifying anchor wins; later anchors referencing the same
candidate are recorded as duplicate-candidate rejections. Overlapping and nested
zones from different candidate candles remain separate and are reported rather
than merged.

## 4. Lifecycle

Lifecycle observation starts on the first source bar after the anchor and lasts
at most 50 source bars.

- `first_touch_at`: the first later bar whose wick overlaps the zone.
- `midpoint_touch_at`: for bullish zones, low reaches the midpoint; for bearish
  zones, high reaches it.
- `full_mitigation_at`: bullish low reaches the lower/distal boundary or bearish
  high reaches the upper/distal boundary.
- `invalidation_at`: bullish close is below the lower boundary or bearish close
  is above the upper boundary.
- If full mitigation and close invalidation occur on the same bar, invalidation
  is the terminal status and both observation timestamps are retained.
- Otherwise, full mitigation is terminal. An uncompleted zone expires after 50
  observed bars or is `active_at_sample_end` when fewer than 50 bars remain.

Touch, mitigation, and invalidation timestamps use the later bar's
`available_at`, never its opening timestamp.

## 5. Registered sensitivities

- Candidate lookback: 3, 6 primary, and 9 bars. Agreement keys include both the
  anchor and selected candidate, so selecting a different candle is a mismatch.
- Maximum lifecycle age: 25, 50 primary, and 100 bars. Agreement compares the
  terminal status of common zones.
- Geometry diagnostic: full-wick primary versus candle-body range. Median price
  interval intersection-over-union must be at least 50%.

None of these comparisons inspects future return.

## 6. Phase-0.2 gates

- zero point-in-time and lifecycle invariant failures;
- at least 95% valid upstream bars;
- at least 70% of eligible anchors find a deterministic candidate;
- at least 30 created Order Blocks per eligible timeframe/year;
- at least 70% Jaccard agreement for lookback and lifecycle sensitivities; and
- at least 50% median geometry overlap for the registered body-range diagnostic.

Passing means only that Order Blocks may enter Phase 1 as an ablation candidate.
It does not make Order Blocks mandatory and does not establish predictive edge.
