# Temporary Data Baseline — 2024–2025

**Audit status:** valid
**Price source:** HistData-derived GBPUSD Bid/Ask ticks
**Role:** temporary development proxy, not Exness account history
**Interval:** `[2024-01-01, 2026-01-01)`

The repository-local `data` symlink points to the existing gitignored data
directory in the auction/value/volume project. No raw or processed market data
is copied or committed.

## Audit result

```text
expected months             24
available months            24
M5 bars                     149,526
first timestamp             2024-01-01 22:00:00 UTC
last timestamp              2025-12-31 21:55:00 UTC
missing months              0
schema errors               0
duplicate timestamps        0
crossed Bid/Ask closes      0
median M5 median spread     0.8 pips
95th-pct M5 median spread   1.7 pips
maximum M5 median spread    36.5 pips
```

The maximum includes illiquid/week-boundary conditions. Future strategy phases
must apply session eligibility and spread guards point-in-time rather than
dropping expensive trades after seeing their outcome.

## Execution interpretation

The historical Bid/Ask difference is retained as the temporary spread proxy.
On top of quote-side execution, the simulation will charge:

```text
commission per side     0.35 pip equivalent
round-trip commission   0.70 pip equivalent
primary slippage        0.10 pip per side
stress slippage         0.20 pip per side
```

This is deliberately conservative but is not an assertion that Exness would
have quoted the same historical spread. Account-aligned Exness data will replace
the price adapter later while the market-structure definitions stay frozen.

Reproduce the audit:

```bash
.venv/bin/python -m gbpusd_structure audit-data
```
