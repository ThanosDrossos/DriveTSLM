## Consistency-checker evaluation (azure.gpt-5-mini, 104/105 runs ok)

- contradiction detection: precision **0.784**, recall **0.784** (FP rate 0.208, confusion {'tp': 40, 'fp': 11, 'fn': 11, 'tn': 42})
- abstention rate: **0.389** of assertion verdicts
- citation validity: mean **0.9646**, fully grounded runs 20/104, uncited claims total 443
- cost/case: **$0.0057** (20827 in / 1252 out tokens)
- run-to-run agreement (majority share across reps): **0.8762**

| injected error | runs | detected | recall | localized to right assertion |
|---|---|---|---|---|
| claimed_braking_absent | 9 | 6 | 0.667 | 6 |
| event_count_mismatch | 9 | 4 | 0.444 | 4 |
| speed_mismatch | 15 | 14 | 0.933 | 11 |
| understated_severity | 12 | 12 | 1.0 | 11 |
| wrong_impact_direction | 6 | 4 | 0.667 | 2 |
