# Phase 1.2 Stage A — Construction Coverage Results

**Status:** completed without P&L access  
**Coverage fingerprint:** `accd1392cff3c949`  
**Parent fingerprint:** `90d1e369b427d3d8`  
**Period:** 2024 construction only

## Outcome

The coverage engine read only the registered safe candidate fields. Its output
contained no return, exit, win, commission, slippage, or P&L columns and had
zero invariant failures.

| Filter | Trades | Mean/month | Coverage decision |
|---|---:|---:|---|
| F1 displacement | 275 | 22.92 | eligible |
| F2 H1 opposition veto | 343 | 28.58 | too frequent |
| F3 H4 opposition veto | 327 | 27.25 | too frequent |
| F4 H1+H4 opposition veto | 288 | 24.00 | eligible |
| F5 displacement + H4 veto | 223 | 18.58 | too sparse |
| F6 displacement + H1+H4 veto | 190 | 15.83 | too sparse |

F1 selected 120 London and 155 New York sessions, split almost exactly between
138 long and 137 short signals. F4 selected 114 London and 174 New York
sessions, with 153 long and 135 short signals.

Only F1 and F4 may enter Stage B construction P&L. The other filters cannot be
restored based on later performance.

Generated count-only evidence is gitignored under
`artifacts/phase1_2/coverage/accd1392cff3c949/`.
