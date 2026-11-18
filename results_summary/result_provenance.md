# Result provenance

The CSV files in this directory are compact exports of the dissertation's retained formal
summary. The selected raw timings, run summaries, manifests, and correctness records are
available under `evidence/`.

## Common aggregation rule

Each formal condition has 20 recorded repetitions. The values are sorted, the fastest five
and slowest five are removed, and the arithmetic mean of the middle ten is reported. Times
are milliseconds. The database metric is TigerGraph `query_status.elapsedTime`; no synthetic
equivalent of Neo4j DB Hits is reported.

## Included evidence

| Workload | Included records |
|---|---|
| Q1--Q22 | Raw 20-run timings, trimmed summaries, recorded parameters, and available run manifests at SF 0.01, 0.1, and 1 |
| Query correctness | Retained validation reports for the representative direct queries and Q11, Q14, Q16, Q21, and Q22 |
| Entity Integrity | Raw timings, summaries, parameters, manifests, global zero-violation checks, and the retained reversible positive control |
| Referential Integrity | Raw and summary files for Cc, Oc, Pc, and Sc at all three scales, plus cleanup checks |
| RF1/RF2 | Raw round records, summaries, and round-level correctness reports for the completed scale-dependent series |

`evidence/query_source_map.csv` maps each analytical result to its source in the full project.
`evidence/evidence_manifest.csv` provides file sizes and SHA-256 digests. Repeated output
dumps, failed attempts, retry logs, and exploratory runs are excluded from the review copy.

## Interpretation limits

- Formal completion is not treated as independent output validation.
- Independent SF 0.01 source-data validation is retained for one representative parameter case from each of Q1, Q3, Q6, Q7, and Q18; additional checks cover Q11, Q14, Q16, Q21, and Q22.
- Entity global zero counts and reversible positive controls support the implemented detectors; they do not show native TigerGraph enforcement.
- Referential Integrity cleanup checks do not constitute a per-vertex before/after audit.
- The included RF series is the completed scale-dependent experiment with 15, 150, and 1,500 Orders per round at SF 0.01, 0.1, and 1. The retained full-project sources are `sf001_graph/20261022_171854_008909`, `sf01_graph/20261022_190332_704175`, and `sf1_graph/20261023_005208_810832`.
