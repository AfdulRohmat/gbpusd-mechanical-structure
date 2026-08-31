# Technical Plan — Phase 3 Price-Action State Machine

**Status:** preregistered before state and setup coverage  
**Branch:** `phase/03-price-action-state-machine`  
**Evidence stage:** 2024 definitions and return-blind coverage only

## 1. Objective

Phase 3 translates the rules described in the supplied
[price-action video](https://youtu.be/TegF3yYjnng) into a causal and testable
state machine. The transcript is a hypothesis source, not empirical evidence.
Claims such as “most” or “90%” of range breakouts failing are not imported as
facts or optimization targets.

This is a materially new hypothesis after Phase 2 closed the repository's
single-event BOS/CHoCH directional thesis. Phase 3 combines sequential context,
pullback state, location, and confirmation. It does not repair or relabel P3.

The first stage answers only:

1. Can every state transition be generated point-in-time?
2. Do the rules classify enough London/New York observations?
3. Do high-probability setup labels occur and trigger often enough to support a
   later cost-aware test?

No forward return, stop, target, R multiple, or P&L may be read in this stage.

## 2. Operationalization boundary

The video contains discretionary phrases that cannot be coded literally:
“nicely fitting trendline,” “healthy range,” “good signal bar,” and “close
enough to a new extreme.” Phase 3 freezes one explicit interpretation before
coverage:

- M15 defines regime and market geometry;
- M5 defines pullback attempts and executable signal bars;
- EMA21 is only a key-entry-location tool, never a directional signal;
- confirmed pivots replace manually drawn anchor points; and
- every decision is available only after its source candle closes.

Different interpretations may be researched later, but cannot be substituted
after seeing Phase-3 coverage or returns.

## 3. M15 regime states

The state space is mutually exclusive:

```text
undetermined
trend_up_active
trend_down_active
trend_up_break_pending_extreme
trend_down_break_pending_extreme
post_up_extreme_transition
post_down_extreme_transition
range
range_break_up_pending
range_break_down_pending
range_break_up_wait_retest
range_break_down_wait_retest
```

### 3.1 Proven trend

A bullish trend requires the latest confirmed M15 swing high to be `HH` and
the latest confirmed swing low to be `HL`. A bearish trend requires `LH` and
`LL`. Swings use the existing causal `2-left/2-right` definition.

For an uptrend, the projected trendline joins the last two confirmed rising
swing lows. For a downtrend, it joins the last two confirmed falling swing
highs. Projection begins only after the second pivot has been confirmed.

### 3.2 Trendline rule

An uptrend line breaks when a completed M15 candle closes more than `0.05 ATR`
below its causal projection; a downtrend line breaks symmetrically above it.
The directional bias does not reverse at that break. It enters
`trend_*_break_pending_extreme`.

The previous trend's final extreme is fulfilled when price reaches or comes
within `0.10 ATR` of the extreme known at the trendline break. This admits the
video's near-equal/double-top example without an unbounded visual tolerance.
The machine then enters `post_*_extreme_transition`, where new with-trend setup
selection pauses until a proven trend or range appears.

The video describes the final extreme as likely, not logically guaranteed. A
fully proven opposite HH/HL or LH/LL sequence may therefore override a pending
extreme. Such overrides are counted explicitly rather than forcing the old bias
forever.

### 3.3 Trading range

A causal range candidate uses the preceding 20 completed M15 bars and requires:

- at least two confirmed swing highs and two confirmed swing lows;
- each side clustered within `0.25 ATR`;
- width between `1.0` and `4.0 ATR`; and
- directional efficiency no greater than `0.35`, where efficiency is absolute
  net close movement divided by summed absolute close movement.

The median high and low clusters become frozen resistance and support. A range
has priority only when no proven active trend is controlling the bar. Its
middle 35–65% is a no-entry zone.

### 3.4 Range breakout lifecycle

A close beyond a boundary plus `0.05 ATR` creates `range_break_*_pending`.

- A close back inside the frozen range within six M15 bars is a
  `failed_range_break` and restores `range`.
- Two consecutive buffered closes outside produce
  `range_break_*_wait_retest`.
- A retest within six bars must touch the frozen boundary within `0.10 ATR` and
  close on the breakout side. It emits `accepted_breakout_pullback`.
- Re-entry inside the range invalidates acceptance and restores `range`.
- An unresolved breakout expires to `undetermined`; it is not silently called
  continuation.

## 4. M5 setup machine

### 4.1 With-trend second entry

In `trend_up_active` or `trend_up_break_pending_extreme`, a pullback begins with
a lower-low M5 bar. The first subsequent break above the prior bar high is the
first long reversal attempt. If it fails and price makes a new pullback low by
at least `0.05 M15 ATR`, the next qualifying bullish reversal attempt is the
second-entry signal. The bearish definition is mirrored.

Attempts expire after 18 M5 bars or when price resumes beyond the prior trend
extreme. The counter-trend second-entry failure described in the video is
recorded as confluence on the same with-trend event, not admitted as an
independent fourth setup family.

### 4.2 Key entry point

A with-trend signal must intersect at least one causal key-entry source within
`0.20 M15 ATR`:

- M15 EMA21;
- the projected M15 trendline; or
- for range families, the frozen range boundary.

### 4.3 Signal-bar rule

A long signal bar must close above its open, have body at least 50% of total
range, close in the upper 35% of its range, and span at least `0.25 M5 ATR`.
A short signal is mirrored. Zero-range bars cannot qualify.

Entry is not assumed at signal close. A stop-entry trigger is `0.10 pip` above
the long signal high or below the short signal low and remains valid for the
next two M5 bars. Trigger occurrence is coverage metadata only, not a trade.

### 4.4 Range setups

A confirmed failed M15 breakout waits up to three completed M5 bars for an
inward signal bar at the frozen boundary. Accepted breakout-pullback events use
the same wait but require a signal in the breakout direction. Both use the same
stop-entry trigger contract.

## 5. Congestion veto and selection

A setup is vetoed when the latest six completed M5 bars span no more than
`1.50 M5 ATR` and their mean adjacent-bar overlap is at least `0.60`. This makes
the video's “do not trade stacked bars” rule explicit.

Raw signals remain in the audit. Chronological selected coverage is capped at
one setup per London session and two per New York session, matching the user's
previous frequency constraint. No outcome-based ranking is allowed.

## 6. Return-blind gate

The state-machine stage advances only if:

- every causal and membership invariant passes;
- at least 60% of in-session M15 bars receive a non-undetermined state;
- at least 120 selected setup signals and 120 triggered setups occur in 2024;
- at least 50% of selected signals trigger;
- London, New York, long, and short each contain at least 30 triggers.

The desired—not mandatory—frequency is 240–480 triggers per year, approximately
20–40 per month. Passing coverage permits only a separately frozen construction
P&L phase. It does not establish edge.

## 7. Invariants

- Only the twelve construction-year files are opened.
- Every pivot and trendline anchor is available by the bar using it.
- Exactly one M15 state exists per eligible in-session bar.
- Frozen range boundaries do not move during their breakout lifecycle.
- M5 setup features are available by signal close.
- Entry triggers occur strictly after signal availability.
- Congestion and key-entry tests use completed bars only.
- Session caps are enforced chronologically without return access.
- No artifact contains forward return, exit, R, P&L, profit factor, or win-rate
  fields.

Any invariant failure invalidates the coverage result.
