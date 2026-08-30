# Technical Plan — Phase 1.4 Structural-Invalidation Stop Ablation

**Status:** preregistered before structural-stop returns  
**Branch:** `phase/01-4-structural-stop-ablation`  
**Signal parent:** Phase 1.1 fingerprint `90d1e369b427d3d8`  
**Diagnostic parent:** Phase 1.3 fingerprint `c9475ab43c8aba4a`

## 1. Research question

Phase 1.3 showed that the `1 ATR` stop was followed by the original `+2 ATR`
destination in 27.31% of construction stop-first paths and 23.28% of historical
replication stop-first paths. Phase 1.4 asks whether a causal structure
invalidation level handles that noise more effectively after complete execution
costs.

This phase changes stop placement only. It preserves the frozen P3 signals,
first-signal-per-session selection, entry timing, London/New York cutoff,
observed Bid/Ask pricing, commission, slippage, and stop-first intrabar policy.
It does not add setup filters or increase trade frequency.

## 2. Causal structural invalidation

For every frozen M15 BOS/CHoCH signal, locate the latest confirmed opposing M15
swing available at the decision timestamp:

- long: latest confirmed M15 swing low;
- short: latest confirmed M15 swing high.

The existing state machine defines a continuation BOS using this latest
opposing swing as the protected swing. A CHoCH finishes in `transition`, so its
latest opposing swing is explicitly described as an invalidation proxy rather
than a confirmed protected swing for the new direction.

Point-in-time constraints are frozen:

- swing `available_at <= decision_at`;
- swing pivot `event_at < decision_at`;
- no future swing may replace it;
- the parent signal's source break must reproduce in the current causal labels.

The hard-stop level uses the executable quote extrema inside the M15 swing bar:

```text
long stop  = minimum Bid low of swing M15 bar - 0.10 signal ATR
short stop = maximum Ask high of swing M15 bar + 0.10 signal ATR
```

Observed spread is already embedded in these quote extrema. The buffer is
frozen before accessing structural-stop returns. No minimum or maximum stop
distance filter is allowed. A missing swing or a stop on the wrong side of entry
is an audit failure, not a silently skipped trade.

## 3. Frozen variants

| ID | Stop | Target | Role |
|---|---|---|---|
| `p3_atr_1_target_2atr` | `1 signal ATR` | `2 signal ATR` | frozen parent baseline |
| `p3_structure_target_2atr` | structural invalidation | `2 signal ATR` | stop-geometry diagnostic |
| `p3_structure_target_2r` | structural invalidation | `2 × structural risk` | strategy candidate |

The fixed-`2 ATR` variant isolates whether the new stop lets the original price
destination resolve first. Its reward:risk is variable and it cannot be
selected as a strategy.

The `2R` variant preserves the user's intended `1:2` bracket. Because a wider
stop also creates a farther target, it is the only selectable strategy variant.

## 4. Fixed-dollar risk reporting

Every structural trade is normalized by its actual entry-to-stop distance.
Theoretical position size for a `$30` geometric risk is:

```text
raw lots = 30 / (stop pips × 10 USD per pip per standard lot)
```

Lot quantization is disabled because the temporary feed is not the final Exness
MT5 execution dataset. Commission and slippage can make a stopped trade lose
slightly more than `$30`; this is retained rather than clipped to `-1R`.

## 5. Staged evidence lock

### Stage A — 2024 construction

Both structural variants may be simulated on 2024. Only
`p3_structure_target_2r` can qualify. It advances only if:

- all invariants pass;
- its signal/trade count matches parent P3;
- mean full-cost R per trade is positive;
- profit factor exceeds one; and
- mean R per common opportunity exceeds parent P3.

If any condition fails, Phase 1.4 stops and does not calculate 2025
structural-stop returns.

### Stage B — historical replication

Replication remains locked until a committed selection file records a qualified
construction candidate. The 2025 period is not a pristine unseen holdout because
its Phase 1.3 excursion paths have already been inspected; it remains a frozen
historical replication of the exact structural rule.

The candidate must then have positive primary and stress expectancy, profit
factor above one, improvement over parent P3, positive expectancy in both
sessions and directions, a positive day-cluster opportunity-mean 95% CI, and no
single best month supplying more than half of all positive monthly R.

## 6. Execution rules

- Long enters at observed Ask open and exits on Bid.
- Short enters at observed Bid open and exits on Ask.
- Entry and exit each receive frozen slippage.
- Round-trip commission remains `0.70 pip`.
- A stop gap fills at the worse observed executable open.
- A target gap receives no price improvement.
- If stop and target appear within the same M5 candle, stop wins.
- Open positions are force-closed at the frozen session cutoff.

## 7. Invariants

- Parent P3 signals are reproduced one-to-one.
- Source BOS/CHoCH event type, direction, and decision time match.
- Every structural swing existed by decision time and pivoted before it.
- Long/short structural stops lie on the correct side of executable entry.
- Structural trade count equals parent trade count.
- Entry timestamps and prices reproduce the parent simulator.
- No construction artifact contains 2025 structural-stop return fields.
- Replication cannot run without a frozen construction selection.

Any invariant failure invalidates the stage regardless of performance.
