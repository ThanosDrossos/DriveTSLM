## Consistency-checker evaluation (azure.gpt-5-mini, 105/105 runs ok)

- contradiction detection: precision **0.857**, recall **0.824** (FP rate 0.13, confusion {'tp': 42, 'fp': 7, 'fn': 9, 'tn': 47})
- abstention rate: **0.402** of assertion verdicts
- citation validity: mean **0.9558**, fully grounded runs 16/105, uncited claims total 574
- cost/case: **$0.0059** (21780 in / 1308 out tokens)
- run-to-run agreement (majority share across reps): **0.8857**

| injected error | runs | detected | recall | localized to right assertion |
|---|---|---|---|---|
| claimed_braking_absent | 9 | 6 | 0.667 | 6 |
| event_count_mismatch | 9 | 8 | 0.889 | 8 |
| speed_mismatch | 15 | 15 | 1.0 | 13 |
| understated_severity | 12 | 12 | 1.0 | 12 |
| wrong_impact_direction | 6 | 1 | 0.167 | 0 |
