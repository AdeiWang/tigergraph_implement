# SF 1 Query Timing Stability

This is a descriptive secondary analysis of the retained 20 raw database-time
observations for each formal Q1--Q22 SF 1 workload. It does not replace the
pre-specified trimmed mean used for the primary results.

- Queries analysed: 22
- Median coefficient of variation: 7.42%
- Minimum coefficient of variation: 3.30%
- Maximum coefficient of variation: 21.22%

## Five largest coefficients of variation

| Query | CV | Median (ms) | IQR (ms) |
|---|---:|---:|---:|
| Q13 | 21.22% | 218.0 | 53.75 |
| Q6 | 19.65% | 223.0 | 53.0 |
| Q16 | 12.79% | 449.0 | 52.75 |
| Q7 | 10.09% | 13851.0 | 1245.75 |
| Q2 | 9.78% | 1056.5 | 177.25 |

CV is the sample standard deviation divided by the untrimmed raw mean. Q11 and
Q22 use the sum of their two database-stage elapsed times, consistent with the
formal database metric. Client-side finalisation remains excluded.
