# Result provenance

The CSV files in this directory are compact exports of the dissertation's retained formal
summary. They are provided so that the reported values can be reviewed without uploading the
TPC-H datasets or every generated result file.

## Common aggregation rule

Each formal condition has 20 recorded repetitions. The values are sorted, the fastest five
and slowest five are removed, and the arithmetic mean of the middle ten is reported. Times
are milliseconds. The database metric is TigerGraph `query_status.elapsedTime`; no synthetic
equivalent of Neo4j DB Hits is reported.

## Local evidence sources

| Summary | Retained source in the full project | Evidence not copied here |
|---|---|---|
| Q1--Q20 | `results/query_benchmarks/` and query manifests | Timestamped raw 20-run CSV files |
| Q11 | `results/query_benchmarks_final/q11_two_stage/` | Complete per-run outputs and independent validation details |
| Q21/Q22 | `results/query_benchmarks_final/` | Complete final CSV outputs and validation reports |
| Entity Integrity | `entity_integrity/results/` | Raw benchmark files and global-verification JSON/CSV files |
| Referential Integrity | `referential_integrity/results/` | Raw files for every chain, scale, and activation percentage |
| RF1/RF2 | `queries_and_refresh_operations/rf1_rf2/results/` | Per-round raw and correctness JSON files |

The omitted directories contain generated evidence rather than implementation source and can
be supplied separately if detailed auditing is required.

## Interpretation limits

- Formal completion is not treated as independent output validation.
- Additional validation is retained for Q11, Q14, Q16, Q21, and Q22.
- Entity global zero counts establish that no checked duplicate was found; they do not show native TigerGraph enforcement or a retained positive-control test.
- Referential Integrity cleanup checks do not constitute a per-vertex before/after audit.
- The included RF series is the historical fixed-batch experiment with 15 Orders per round at every scale.
