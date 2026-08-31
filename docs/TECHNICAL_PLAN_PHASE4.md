# Technical Plan — Phase 4 Structural-Stop `2 ATR` Management

**Status:** preregistered before 2025 management returns  
**Branch:** `phase/04-structure-stop-2atr-improvement`  
**Signal parent:** Phase 1.1 fingerprint `90d1e369b427d3d8`  
**Structural parent:** Phase 1.4 construction fingerprint `41fe02f5ef90868b`

## 1. Research question

Phase 1.4's structural stop with a fixed `+2 signal ATR` target raised 2024 win
rate to `45.05%`, but remained negative at `-0.147R/trade` and profit factor
`0.616`. Its median structural risk was `2.87 ATR`, so the median target was
only `0.697R` before costs.

Phase 1.5 improved entry geometry with M5 FVG mitigation, but removed fast
continuations, reduced win rate to `41.20%`, and remained negative. Phase 4
therefore does not modify entry or select another signal subset. It tests one
loss-compression rule while preserving the immediate entry, structural hard
stop, absolute `+2 ATR` target, and session cutoff.

The question is:

> After a trade completes half of its path to the target, can a causal
> breakeven protection state reduce full-stop losses enough to create positive
> full-cost expectancy without damaging the target winners?

## 2. Evidence boundary

The management candidate was designed after seeing the 2024 Phase 1.4 result.
Its 2024 return is permanently closed in this phase. Evaluation uses the frozen
2025 P3 parent sample only.

The 2025 period is **not** a pristine program-wide holdout: earlier phases have
already reported other P3 and path outcomes for that year. However, Phase 1.4
never opened 2025 structural-stop returns, and this exact management rule has
not been evaluated there. A pass can justify Exness/forward validation, not a
claim of proven edge.

The frozen parent contains 383 P3 signals:

```text
membership SHA-256 = d7bf7882c2cc08184d34c41b47ee91dd6b41cc8cc98494736f2fe148cfe2753a
London              = 173
New York            = 210
Long                = 204
Short               = 179
```

Membership is the SHA-256 of sorted newline-delimited `signal_id` values. No
event, session, direction, hour, stop-distance, or outcome filter is permitted.

## 3. Frozen bracket

Both variants reproduce the Phase 1.4 diagnostic geometry:

- immediate entry at the first executable M5 open at/after the P3 decision;
- long entry on Ask and short entry on Bid;
- structural hard stop at the latest causally confirmed opposing M15 swing,
  plus the frozen `0.10 signal ATR` buffer;
- absolute target `2 signal ATR` from the immediate reference entry; and
- forced exit at the registered session cutoff.

The target never moves. Dollar risk remains `$30` relative to the original
entry-to-structural-stop distance. Commission and slippage can make realized
loss exceed the geometric R amount.

## 4. Frozen variants

### M0 — static baseline

`structure_stop_target_2atr_baseline` keeps the structural stop unchanged until
stop, target, or session cutoff.

### M1 — completed-bar breakeven protection

`structure_stop_target_2atr_be_after_1atr` starts with the same structural hard
stop. A protection trigger occurs when a completed M5 bar reaches `+1 signal
ATR` from entry on the executable exit quote:

```text
long trigger  = Bid high >= entry Ask + 1 signal ATR
short trigger = Ask low  <= entry Bid - 1 signal ATR
```

The trigger is exactly half of the frozen `+2 ATR` target distance. It was not
selected from a 2024 threshold sweep.

Breakeven becomes active only from the **next** M5 bar. The protected stop is
the pre-slippage entry reference, so a breakeven exit remains slightly negative
after slippage and commission. Activation is irreversible.

## 5. Intrabar and gap ordering

On the bar that first reaches `+1 ATR`, the original bracket remains active for
the whole bar:

1. structural stop gap/touch;
2. target gap/touch; then
3. schedule breakeven for the next bar.

This prevents using the completed bar's high/low to retroactively move a stop
inside the same bar. Once protection is active, each later bar resolves:

1. gap through the protected stop at the worse executable open;
2. protected-stop touch;
3. target touch; or
4. continue.

The existing conservative stop-first policy applies whenever stop and target
are both observable in one M5 bar.

## 6. Execution model

- observed HistData Bid/Ask remains the temporary path proxy;
- it is not described as historical Exness spread;
- commission is `0.35 pip` per side;
- primary slippage is `0.10 pip` per side;
- stress slippage is `0.20 pip` per side;
- stop gaps fill at the worse executable open;
- targets receive no positive gap improvement; and
- swap remains disabled because every trade is closed intraday.

## 7. Historical decision gate

M1 advances to Exness or genuinely forward validation only if all conditions
hold in 2025:

- zero invariant failures and exact 383-signal membership;
- positive primary mean net R and profit factor above one;
- positive paired mean improvement over M0;
- the session-date cluster-bootstrap 95% CI lower bound of paired improvement
  is above zero;
- positive stress expectancy;
- positive expectancy in London, New York, long, and short scopes;
- maximum drawdown below M0; and
- no best month supplies more than 50% of total positive monthly R.

Relative loss reduction alone is insufficient. If any condition fails, the
registered action is to close this management repair rather than tune the
trigger, breakeven level, or subgroup.

## 8. Invariants and outputs

- Only P3 signals from 2025 receive outcome simulation.
- 2024 bars may provide causal indicator/swing warmup only; M1 2024 returns are
  neither calculated nor written.
- M0 and M1 have identical signal membership, entry reference, structural stop,
  target, and raw price path.
- Every structural swing existed by decision time and pivoted before it.
- The `+1 ATR` trigger can activate protection only on a strictly later bar.
- No trade observes a bar at or beyond its registered cutoff.
- Primary and stress runs use identical raw exits and differ only in modeled
  fill friction.

The runner writes signal membership, structural mappings, primary/stress
trades, paired differences, scope/month/exit summaries, bootstrap evidence, and
a machine-readable gate decision.
