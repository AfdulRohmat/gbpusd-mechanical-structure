# Technical Plan — Phase 2 Directional Signal Edge Audit

**Status:** preregistered before forward-return calculation  
**Branch:** `phase/02-directional-signal-audit`  
**Construction period:** 2024 only

## 1. Research question

Phase 2 asks whether the causal M15 primitives underneath P3 contain directional
information before entry refinement, stops, targets, spread, commission, or
slippage are introduced.

The tested claim is deliberately narrower than “SMC works.” It is:

> After a registered M15 structure event in London or New York, does price move
> farther and more consistently in the event's predicted direction than chance
> and simple price baselines?

If the answer is no at the gross mid-price level, FVG, Order Block, ATR stops,
and execution tuning cannot be treated as repairs for this signal family.

## 2. Evidence boundary

Only events and forward paths whose event year is 2024 may enter this audit.
No 2025 Phase-2 forward return may be calculated during construction.

The repository has already reported 2025 P3 paths in earlier phases, notably
Phase 1.1 and Phase 1.3. Consequently, 2025 is not a pristine holdout for the
overall research program. If Phase 2 advances, it can serve only as a frozen
historical/quasi-replication for the new primitive rule. A genuine forward
lockbox requires data not previously inspected under this program.

## 3. Registered event primitives

All events use completed, eligible M15 bars and are available no earlier than
the bar close.

1. **BOS:** the existing state machine's close-confirmed continuation break.
   Its predicted direction is the break direction.
2. **CHoCH:** the existing close-confirmed break of a protected opposing swing.
   Its predicted direction is the break direction.
3. **Liquidity sweep:** the wick exceeds the latest swing known by the start of
   the M15 bar by at least `0.05 ATR`, then the same bar closes back inside the
   level. A high sweep predicts down and a low sweep predicts up. The swing is
   consumed after its first qualifying excursion; a bar sweeping both sides is
   excluded as ambiguous.
4. **Displacement:** an eligible completed M15 candle with absolute body at
   least `0.80 ATR`. Its predicted direction is the candle-body direction.

The diagnostic table retains all events. The primary inferential sample keeps
only the first event of each primitive in each London or New York session. This
prevents repeated same-session events from manufacturing sample size and keeps
the unit comparable with the prior one-trade-per-session objective.

## 4. Forward outcome

The entry reference is the first M5 mid open at or after event availability.
The exit reference is the exact M5 mid open at `15`, `30`, `60`, `120`, and
`240` minutes. Missing exact-horizon observations are not interpolated.

For predicted direction `d` in `{+1, -1}`:

```text
signed forward return = d × (future mid - entry mid) / frozen M15 ATR
```

MFE and MAE use M5 mid highs/lows over the same fixed horizon. The `60` minute
return is primary; other horizons diagnose persistence. Within `240` minutes,
the audit also records whether `+1 ATR` or `-1 ATR` is touched first. A same-M5
bar touch remains ambiguous rather than guessing intrabar order.

This is a direction audit, not a tradable P&L simulation. It intentionally
excludes Bid/Ask spread, commission, slippage, stops, targets, and sizing. Gross
failure is therefore stronger evidence against the signal than net failure.

## 5. Simple baselines at the same timestamps

Each primary event is evaluated against:

- the event's own predicted direction;
- a reproducible seeded random direction plus a 10,000-resample random null;
- session momentum from session-open mid to the completed event-bar close;
- the inverse session mean-reversion direction; and
- a close breakout beyond the preceding four completed M15 bars, reported as
  no prediction when neither side breaks.

The breakout baseline is diagnostic when it emits a direction because its
coverage need not equal the other rules. Session momentum and mean reversion
are paired on every non-flat event timestamp and participate in the gate.

## 6. Registered strata

Results are reported by primitive, session, predicted direction, H1/H4 context
alignment, and displacement strength (`<0.8`, `0.8–1.2`, `>=1.2 ATR`). These are
diagnostics only. No observed subgroup can become a strategy filter inside
Phase 2.

BOS is the registered continuation event and CHoCH the registered reversal
event. Comparing them is descriptive; the better observed label is not a
post-hoc winner unless its complete primitive-level gate passes.

## 7. Advancement gate

Each primitive is judged at the first-event-per-session level. Advancement
requires all of the following:

- at least 120 primary events in 2024;
- positive mean signed return at 60 minutes;
- the session-date cluster-bootstrap 95% lower bound above zero;
- mean return above the 97.5th percentile of the random-direction null;
- `+1 ATR` first-touch rate above 50% among resolved 240-minute paths;
- positive 60-minute mean in London, New York, long, and short strata, each
  with at least 30 observations;
- positive mean in at least four of five registered horizons; and
- positive paired 60-minute improvement over both session momentum and session
  mean reversion.

At most one primitive may be frozen for historical replication, ranked by its
primary 60-minute cluster-bootstrap lower bound. If none passes, the current
BOS/CHoCH/sweep/displacement directional thesis closes. Adding EMA, RSI, FVG,
or Order Block filters would then require a materially new hypothesis rather
than another repair of P3.

## 8. Invariants

- No event or outcome row has an event year other than 2024.
- Event availability never exceeds the entry timestamp.
- Sweep source swings were available by the start of their event bars.
- Exact-horizon exits and path membership contain no interpolation or future
  overlap.
- Primary events are unique by primitive and session opportunity.
- Baseline directions use information available by the event decision.
- All normalized outcomes use positive frozen event ATR.
- Construction artifacts contain no Phase-2 2025 forward-return columns or
  rows.

Any invariant failure invalidates the audit regardless of the descriptive
result.
