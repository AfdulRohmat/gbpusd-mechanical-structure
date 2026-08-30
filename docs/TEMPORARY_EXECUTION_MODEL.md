# Temporary Exness Raw Spread Execution Model

## What is simulated

Until the account-aligned Exness MT5 export is available, the project uses:

```text
market path       = existing HistData GBPUSD midpoint/Bid/Ask bars
spread            = observed HistData Bid/Ask spread
commission        = USD 3.50 per standard lot per side
commission pips   = 0.35 pip per side for GBPUSD
slippage primary  = 0.10 pip per side
slippage stress   = 0.20 pip per side
intrabar priority = stop first
```

A round trip therefore includes `0.70` pip-equivalent commission in addition to
the observed Bid/Ask spread and two-sided slippage.

## Why spread is not overwritten

Exness Raw Spread is variable. Advertising a spread “from 0” does not establish
the historical GBPUSD spread at a particular London/New York decision time.
Replacing the available Bid/Ask path with a constant would create precision that
the evidence does not support.

The existing HistData spread is retained as a conservative proxy and explicitly
reported. It must never be called an Exness historical spread. Primary strategy
reports will later be rerun on the Exness feed without retuning structure rules.

## Quote-side rules

- Long entry executes on Ask; long exits are valued/triggered on Bid.
- Short entry executes on Bid; short exits are valued/triggered on Ask.
- Adverse slippage applies at entry and exit.
- Commission applies at entry and exit independently.
- Stop gaps fill at the first worse executable quote.
- A bar touching stop and target without tick ordering resolves stop-first.
- Swap is disabled only while every strategy closes by the registered intraday
  cutoff. Any later overnight variant requires an explicit swap model.

## Replacement condition

The temporary model is superseded when the Exness MT5 export passes timestamp,
coverage, crossed-quote, and session-spread validation. Feed replacement changes
the data manifest and execution results, not signal definitions or thresholds.
