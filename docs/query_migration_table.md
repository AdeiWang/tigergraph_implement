# Q1--Q22 migration summary

I grouped each query by the main change needed to run it in TigerGraph. The group describes the implementation, not the level of result validation.

| Category | Count | Queries | Meaning |
|---|---:|---|---|
| Direct or near-direct | 16 | Q1--Q7, Q9, Q10, Q12, Q13, Q15, Q17--Q20 | The main query structure is kept. |
| Equivalent rewrite | 3 | Q8, Q14, Q16 | The expression changes but the intended result is kept. |
| Decomposed | 3 | Q11, Q21, Q22 | Multiple database stages or Python processing are needed. |

Q14 is in the rewrite group even though Python calculates its final percentage. Q11 uses the same two-stage version at all three scale factors. Q21 and Q22 use `run_q21_q22_final.py` so their complete output is saved.
