# Phase 1.4 Results — Structural-Invalidation Stop Ablation

**Status:** stopped after construction; replication remained locked  
**Construction fingerprint:** `41fe02f5ef90868b`  
**Parent fingerprint:** `90d1e369b427d3d8`

## Outcome

The structural stop substantially reduced the loss of frozen P3 relative to the
`1 ATR` baseline, but it did not create positive construction expectancy. The
selectable structural-stop `2R` candidate had mean return `-0.143R`, profit
factor `0.667`, and total return `-55.09R` after primary costs.

The stage also recorded one root structural-mapping failure. Under the frozen
contract, either result is sufficient to stop. No selection file was created
and no 2025 structural-stop return was calculated.

## Construction performance

| Variant | Trades | Win rate | Mean R/trade | Profit factor | Total R | Mean R/opportunity |
|---|---:|---:|---:|---:|---:|---:|
| `1 ATR` stop / `+2 ATR` parent | 385 | 27.53% | -0.331 | 0.567 | -127.477 | -0.2451 |
| Structure stop / `+2 ATR` diagnostic | 384 | 45.05% | -0.147 | 0.616 | -56.525 | -0.1087 |
| Structure stop / `2R` candidate | 384 | 36.20% | -0.143 | 0.667 | -55.093 | -0.1059 |

The candidate satisfied only relative improvement over parent P3. It failed
positive mean return, profit factor above one, equal trade count, and zero
invariant failures.

Stress slippage made the candidate slightly worse: mean `-0.153R`, profit
factor `0.649`, and total `-58.89R`.

## Why the structural stop behaved differently

The stop was much wider than the original `1 ATR` assumption:

| Statistic | Structural stop distance |
|---|---:|
| 25th percentile | 2.38 ATR |
| Median | 2.87 ATR |
| 75th percentile | 3.53 ATR |
| 90th percentile | 4.39 ATR |
| Maximum | 7.34 ATR |

At a theoretical fixed `$30` geometric risk, median size fell to approximately
`0.139` standard lot. The smallest theoretical size was `0.030` lot. Lot
quantization was intentionally not applied.

For the selectable `2R` variant, the median target was therefore approximately
`5.74 signal ATR` from entry. Its exits were:

| Exit | Count | Share |
|---|---:|---:|
| Target | 32 | 8.33% |
| Stop | 116 | 30.21% |
| Session cutoff | 236 | 61.46% |

The stop reduced immediate stop-outs, but moving the target proportionally made
the destination difficult to reach before the frozen session cutoff.

The fixed-`+2 ATR` diagnostic reached target 133 times and stopped 104 times,
but timed out 147 times. Its median pre-cost reward:risk was only `0.697:1`
because the target remained fixed while structural risk widened. The resulting
45.05% win rate was consequently insufficient after full costs and time exits.

## Robustness within construction

The selectable `2R` candidate remained negative in every registered session and
direction scope:

| Scope | Trades | Mean R/trade | Profit factor |
|---|---:|---:|---:|
| London | 168 | -0.109 | 0.731 |
| New York | 216 | -0.170 | 0.623 |
| Long | 193 | -0.135 | 0.676 |
| Short | 191 | -0.152 | 0.658 |

Only August produced a positive monthly total (`+1.45R`). The result is not a
single-session, single-direction, or isolated-month edge hidden by aggregation.

## Mapping invariant failure

One short CHoCH signal at the London session on `2024-09-12` produced a causal
opposing-swing level on the wrong side of executable entry:

```text
entry Bid                         1.304320
opposing swing Ask high           1.304250
stop after 0.10 ATR buffer        1.304291
entry-to-stop distance           -0.29 pip approximately
```

This exposes a real limitation of using the latest confirmed opposing swing as
an immediate CHoCH invalidation proxy: causal swing confirmation can lag, and
the latest confirmed high need not remain above a new short entry.

The summary lists six invariant failures, but five are downstream consequences
of this one missing structural trade: two variant count mismatches plus parent
membership, entry-time, and entry-price reproduction mismatches.

The anomaly cannot change the performance decision. A bracketed `2R` trade can
contribute less than `+2R` after costs, while the 384 valid trades totaled
`-55.09R`. Even the most favorable possible missing trade would leave the
candidate strongly negative.

The preregistered action was `audit_failure`; the stop was not repaired with an
entry-relative floor after seeing the row.

## Decision

Phase 1.4 confirms that stop placement was part of P3's loss severity, not the
source of a positive edge. Structural invalidation improved P3 from `-0.331R`
to `-0.143R` per trade, but remained negative after costs and made a true `2R`
target too distant for the available session horizon.

- Qualified construction candidate: **none**.
- Frozen selection file: **not created**.
- 2025 structural-stop replication: **not opened**.
- Phase-1.4 advancement: **none**.

The evidence does not support another post-hoc ATR multiplier or a repair of the
single invalid CHoCH row. A materially different exit model or signal thesis
would be a new phase, not a continuation of this ablation.

Generated evidence is gitignored under
`artifacts/phase1_4/construction/41fe02f5ef90868b/`.

