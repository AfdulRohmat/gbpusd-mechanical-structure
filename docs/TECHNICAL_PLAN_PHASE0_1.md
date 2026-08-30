# Technical Plan — Phase 0.1 Structural State Refinement

**Status:** preregistered before the Phase-0.1 audit  
**Purpose:** correct swing semantics and structural state without inspecting P&L

## 1. Why this refinement exists

The Phase-0 baseline treated any local pivot whose winning margin over a nearby
bar was at most one pip as ambiguous. That mixed two different questions:

1. whether a bar is a mechanically observable pivot; and
2. whether two consecutive structural prices are effectively equal.

This caused 53.91% of M15 and 30.70% of H1 pivots to be discarded. Phase 0.1
separates pivot detection from HH/HL/LH/LL/EQH/EQL relationship labeling. The
one-pip threshold and the existing 5% unresolved-ambiguity gate are not loosened.

## 2. Frozen swing rules

- A pivot still uses two completed bars on the left and two on the right.
- A high must be the exact maximum and a low the exact minimum of its five-bar
  window.
- An exact-price plateau is resolved deterministically to its rightmost member.
  It is recorded as a resolved plateau, not silently duplicated.
- The pivot remains unavailable until the right-hand confirmation bars close.
- Consecutive confirmed highs are labeled:
  - `HH` when the new high is more than one pip above the prior high;
  - `LH` when it is more than one pip below; and
  - `EQH` otherwise.
- Consecutive confirmed lows are labeled:
  - `HL` when the new low is more than one pip above the prior low;
  - `LL` when it is more than one pip below; and
  - `EQL` otherwise.
- The first observable high and low use `H0` and `L0`.

The equality threshold is a relationship classifier. It no longer invalidates
an otherwise deterministic pivot.

## 3. Frozen context state

The context state is derived only from confirmed, point-in-time swing
relationships:

| Latest high relation | Latest low relation | Context state |
|---|---|---|
| HH | HL | bullish |
| LH | LL | bearish |
| EQH | EQL | balance |
| Any other complete pair | Any other complete pair | transition |
| Missing either side | Missing either side | undetermined |

An equality or mixed relationship cannot confirm a directional regime. Once a
new structural relationship is available, the state is recomputed; later data
cannot rewrite an earlier state snapshot.

Daily is restricted to `regime_only`. Daily states may inform later top-down
context but Daily BOS, CHoCH, and FVG events cannot become entry triggers.

## 4. Frozen break state machine

- In bullish context, a close above the active confirmed high plus the frozen
  ATR buffer is BOS.
- In bearish context, a close below the active confirmed low minus the buffer is
  BOS.
- The protected low in bullish context is the latest confirmed `HL`.
- The protected high in bearish context is the latest confirmed `LH`.
- A bullish-context close below its protected low is CHoCH.
- A bearish-context close above its protected high is CHoCH.
- CHoCH moves the state to `transition`; it does not directly assert the
  opposite trend.
- After CHoCH, both a new high relationship and a new low relationship must
  confirm before bullish or bearish context can be re-established.
- A break observed in `undetermined`, `balance`, or `transition` is
  `unclassified_break`, not BOS or CHoCH.
- Each structural level can emit at most one break event until a newly confirmed
  swing supplies a new level.

## 5. Registered definition sensitivities

The original non-return sensitivities remain unchanged:

- swing right bars: 1, 2, and 3;
- break buffer: 0, 0.05, and 0.10 ATR;
- FVG minimum size: 0, 0.10, and 0.20 ATR; and
- S/R cluster tolerance: 0.10, 0.20, and 0.30 ATR.

Phase 0.1 adds relationship-tolerance checks at 0.5 and 1.5 pips around the
frozen one-pip primary definition. Agreement is calculated from timestamped
relationship labels; the comparison does not inspect forward return.

## 6. Phase-0.1 gate

The existing thresholds remain frozen:

- zero point-in-time invariant failures;
- at least 95% valid upstream bar coverage;
- unresolved ambiguity at or below 5%;
- at least 30 events per timeframe/year when the concept is intended as an
  event trigger; and
- at least 70% Jaccard chronology agreement for registered sensitivities.

Because Daily is now explicitly context-only, the minimum-event gate does not
apply to Daily break or FVG trigger counts. Their counts remain reported.

Passing Phase 0.1 means the labels are mechanically usable. It still provides
no evidence of predictive edge.
