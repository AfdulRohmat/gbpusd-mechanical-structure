# Phase 0.1 Results — Structural State Refinement

**Status:** executed; 68 of 69 registered gates passed
**Dataset:** GBPUSD, 2024-01-01 through 2025-12-31
**Run fingerprint:** `bb2be903010a4973`
**Trading/P&L:** intentionally absent

## Outcome

The semantic refinement worked as intended without changing the frozen one-pip
relationship tolerance or the five-percent unresolved-ambiguity gate.

- All 13,232 M15, 3,325 H1, 775 H4, and 128 Daily pivots were deterministically
  resolved.
- Unresolved ambiguity was zero on every timeframe.
- Near-equal prices are retained as `EQH`/`EQL`, not discarded.
- CHoCH now produces `transition`; it never directly asserts the opposite
  regime.
- Daily labels are explicitly ineligible as entry triggers.
- There were zero point-in-time, lifecycle, duplicate-event, or OHLC invariant
  failures.

The overall audit remains `fail` because H1 support/resistance agreement at a
0.10 ATR cluster tolerance was 69.69%, below the preregistered 70% threshold.
The threshold and parameter were not changed after seeing the result.

## Primary label counts

| Timeframe | Swings | Resolved plateaus | BOS | CHoCH | Unclassified breaks | FVG | Entry trigger eligible |
|---|---:|---:|---:|---:|---:|---:|---|
| M15 | 13,232 | 286 | 1,152 | 986 | 2,397 | 8,583 | yes |
| H1 | 3,325 | 32 | 275 | 329 | 561 | 1,909 | yes |
| H4 | 775 | 1 | 88 | 68 | 117 | 512 | yes |
| Daily | 128 | 0 | 17 | 12 | 19 | 54 | **no — context only** |

`Unclassified break` is expected to be more visible than in the baseline: a
break occurring in `undetermined`, `balance`, or `transition` is no longer
misrepresented as BOS or CHoCH.

## Relationship counts

| Timeframe | HH | HL | LH | LL | EQH | EQL |
|---|---:|---:|---:|---:|---:|---:|
| M15 | 2,853 | 2,985 | 2,858 | 2,791 | 863 | 880 |
| H1 | 824 | 818 | 762 | 753 | 82 | 84 |
| H4 | 194 | 196 | 179 | 187 | 9 | 8 |
| Daily | 36 | 31 | 24 | 34 | 1 | 0 |

The remaining two labels per timeframe are the initial `H0` and `L0` anchors.

## Sensitivity evidence

- Swing-window agreement ranged from 75.39% to 84.64%.
- The new 0.5/1.5-pip relationship sensitivity ranged from 88.17% to 100%.
- Break-buffer agreement ranged from 83.33% to 90.00%.
- FVG-size agreement ranged from 75.93% to 84.38%.
- H4 S/R passed at 0.10 ATR (71.64%) and 0.30 ATR (83.30%).
- H1 S/R failed only at 0.10 ATR (69.69%); it passed at 0.30 ATR (87.27%).

All eligible annual event-count gates passed. Sparse Daily breaks and FVGs are
still reported, but no longer gate an entry-trigger role that Daily is forbidden
to perform.

## Disposition before Phase 1

The following concepts are mechanically admissible for strategy construction:

- causal M15/H1/H4 swing relationships;
- bullish/bearish/balance/transition context states;
- protected-swing BOS and CHoCH;
- M15/H1/H4 FVG geometry; and
- H4 support/resistance zones.

Daily is admissible only as slow context. H1 support/resistance is not admitted
to Phase 1 under the current definition. It must either remain excluded or
receive a separately preregistered future refinement; it cannot be rescued by
rounding 69.69% up to the 70% gate.

Full generated evidence is gitignored under
`artifacts/phase0_1/bb2be903010a4973/`, including context-state snapshots,
primary labels, annual/monthly counts, sensitivity comparisons, `summary.json`,
and the hashed manifest.
