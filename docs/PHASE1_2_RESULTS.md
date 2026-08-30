# Phase 1.2 Results — P3 Light-Filter Ablation

**Status:** stopped after construction; replication remained locked  
**Coverage fingerprint:** `accd1392cff3c949`  
**Construction fingerprint:** `9b9664930c5c9591`  
**Parent fingerprint:** `90d1e369b427d3d8`

## Outcome

Phase 1.2 achieved the requested construction frequency of 20–25 trades per
month, but neither coverage-eligible light filter produced positive 2024
expectancy after full costs. No construction winner qualified, so the process
stopped without calculating 2025 filter P&L.

Both stages had zero registered invariant failures.

## Stage A — coverage without P&L

Only F1 and F4 met the frozen 240–300 annual-trade range:

| Filter | 2024 trades | Mean/month | London | New York | Long | Short |
|---|---:|---:|---:|---:|---:|---:|
| F1 displacement | 275 | 22.92 | 120 | 155 | 138 | 137 |
| F4 H1+H4 opposition veto | 288 | 24.00 | 114 | 174 | 153 | 135 |

F2 and F3 were too frequent; F5 and F6 were too sparse. They never received
construction P&L.

## Stage B — construction P&L

| Model | Trades | Win rate | Mean R/trade | Profit factor | Total R | Mean R/opportunity |
|---|---:|---:|---:|---:|---:|---:|
| P3 full-session baseline | 385 | 27.53% | -0.331 | 0.567 | -127.477 | -0.2451 |
| F1 displacement | 275 | 26.91% | -0.346 | 0.561 | -95.040 | -0.1828 |
| F4 H1+H4 opposition veto | 288 | 30.21% | -0.230 | 0.671 | -66.362 | -0.1276 |

Both filters improved mean return per common session opportunity relative to P3
because they traded less. That was only one of three construction requirements.
They failed positive mean trade R and profit factor above one.

F1 was particularly unhelpful: displacement-qualified breaks had slightly worse
mean trade return and win rate than raw P3. Break-bar body size at the frozen
`0.80 ATR` threshold did not identify higher-quality continuation.

F4 removed more losing opportunities than F1 and was the less negative filter,
but remained negative in every session/direction construction stratum. It
therefore cannot be promoted merely because it lost less than P3.

## Evidence lock and decision

- Qualified construction filters: **none**.
- Frozen winner file: **not created**.
- 2025 filter replication: **not opened**.
- Phase-1.2 advancement: **none**.

This is not missing analysis. `stop_without_replication` was the preregistered
action when no construction filter achieved positive expectancy, profit factor
above one, and opportunity improvement.

The result rejects these specific light filters under the current P3 signal and
`1 ATR`/`2R` execution model. It does not authorize selecting London, New York,
BOS, CHoCH, or individual hours after seeing their returns.

Generated count-only and construction evidence is gitignored under:

- `artifacts/phase1_2/coverage/accd1392cff3c949/`; and
- `artifacts/phase1_2/construction/9b9664930c5c9591/`.
