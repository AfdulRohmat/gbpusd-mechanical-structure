# Phase 2 Implementation Notes

## Invalid first run and entry-anchor clarification

The first implementation run (`6378ff754faee3f3`) stopped with two invariant
failures before its performance output was interpreted. Two M15 events became
available at timestamps where the canonical M5 series had no bar. The code
incorrectly required entry to equal event availability even though the frozen
configuration explicitly defines entry as the **first M5 mid open at or after**
event availability.

The implementation was corrected before the valid run:

- delayed entry is permitted exactly as preregistered;
- each fixed forward horizon begins at the actual M5 entry anchor; and
- the complete path must still contain contiguous M5 bars through the exact
  horizon exit, otherwise that event-horizon observation is omitted.

No event definition, threshold, baseline, horizon, gate, or 2024 sample rule
changed. The invalid run is retained only as an audit trail and cannot supply a
research conclusion.
