# Technical Plan — Phase 1.1 Full-Session Setup Revision

**Status:** preregistered before Phase-1.1 P&L inspection  
**Branch:** `phase/01-1-full-session-setups`  
**Parent evidence:** Phase 1 fingerprint `daac4b3ee86ac545`

## 1. Reason for the revision

Phase 1 observed setup-driven P2–P5 models only during the first 90 minutes of
London and New York. That was narrower than the intended rule: enter whenever a
valid setup occurs during the registered session.

Phase 1.1 changes only the setup observation window. It does not reinterpret or
overwrite Phase 1. The earlier 323 P3 signals and nine P4 signals remain the
frozen result of the opening-window experiment.

## 2. Frozen full-session windows

- London setup window begins at 08:00 Europe/London and ends immediately before
  the 08:00 America/New_York open on the same civil date.
- New York setup window begins at 08:00 America/New_York and ends immediately
  before the 17:00 America/New_York FX-day boundary.
- DST is resolved from the same registered IANA timezones.
- A decision must occur before the cutoff. A signal becoming available exactly
  at the cutoff is not executable and is excluded.
- There is no minimum remaining management time. A late valid setup may enter
  on the next available M5 open and is force-closed at the same frozen cutoff.
- Each model independently takes its first candidate satisfying that model's
  complete rules and at most one trade per session.

The London and New York setup windows meet at New York open and do not overlap.

## 3. Models affected

The window revision applies to setup-driven models:

- P2: first causal H4 support/resistance breakout or rejection;
- P3: first causal M15 BOS or CHoCH;
- P4: first M15 BOS/CHoCH whose direction is aligned with both H1 and H4; and
- P5: first aligned M15 BOS/CHoCH with displacement and a same-bar,
  same-direction M15 FVG.

P4 does not stop searching merely because the P3-selected first event was not
aligned. P5 likewise continues after a P4-qualified event without FVG. The
candidate sets are nested, but each model's selected trade may occur at a later
timestamp than its simpler parent's selected trade.

P0 fitted session drift and P1 H4 momentum remain session-open baselines. Their
signal and entry timestamps are intentionally unchanged.

## 4. Rules held unchanged

All other Phase-1 definitions remain frozen:

- 2024 construction and 2025 historical replication;
- observed Bid/Ask quote-side execution;
- 0.10-pip primary and 0.20-pip stress slippage per side;
- 0.35-pip commission per side;
- M15 signal ATR, 1 ATR stop, and 2R target;
- stop-first intrabar ambiguity and gap handling;
- London flat at New York open and New York flat at the FX-day boundary;
- causal H4 zone lifecycle and 0.05 ATR breakout buffer;
- M15 protected-swing BOS/CHoCH definitions;
- exact H1 plus H4 alignment for every P4 candidate;
- same-bar displacement and directional FVG for P5;
- common session-day opportunity panel with no-trade return zero; and
- day-cluster bootstrap and Phase-1 advancement thresholds.

Order Blocks, H1 support/resistance, fundamentals, EMA, RSI, and Daily entry
triggers remain excluded.

## 5. Causality and session invariants

- `session_open_at <= setup_bar_at < decision_at < cutoff_at` for P2–P5.
- Feature `available_at` cannot exceed `decision_at`.
- Entry must be the first observed M5 open at or after `decision_at` and strictly
  before the cutoff.
- A signal/trade belongs to exactly one session window.
- Every P4 source event must exist in the full P3 candidate set and every P5
  source event in the full P4 candidate set. Selected trade timestamps need not
  equal the parent's first selected timestamp.
- P0/P1 counts and decisions must remain identical to the parent run.

Any invariant failure invalidates the run independently of returns.

## 6. Required comparison with Phase 1

The report must show, by model and year:

- opening-window versus full-session signal and trade counts;
- the number of added setups by session hour;
- H1-only, H4-only, and joint alignment counts for P3;
- full-cost expectancy, win rate, profit factor, and opportunity return; and
- whether extra coverage improves or dilutes the parent result.

The larger sample cannot retroactively validate Phase 1.1 unless it passes the
same frozen construction, replication, session, direction, cost-stress,
concentration, and confidence gates.

## 7. Interpretation boundary

If full-session P4 remains sparse, exact H1+H4 alignment is the bottleneck rather
than the opening window alone. If coverage becomes sufficient but expectancy is
negative, the aligned setup lacks evidence under this exit model. Either result
must be retained without post-run window trimming or hour selection.
