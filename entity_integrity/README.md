# Entity Integrity Experiments

This directory keeps correctness and performance tasks separate:

1. `scripts/run_entity_benchmark.py` is the current formal fixed-position
   performance runner. It records TigerGraph `query_status.elapsedTime`, using
   the same timing interface as the Q1-Q22 and Referential Integrity runners.
2. `lineitem/` and `partsupp/` retain the earlier monitor-based scripts and
   XLSX results as historical evidence. They are not used in the final unified
   timing comparison.
3. `scripts/global_verify_*_opencypher.cypher` and
   `scripts/run_global_correctness_verification.py` perform whole-graph
   correctness verification corresponding to the manual forbidden-pattern
   queries in the teacher's `experiments_manual/README.md`.
4. `scripts/run_entity_positive_control.py` tests both global detectors by
   inserting one reversible duplicate in the SF 0.01 graph, confirming that
   the violation count increases, removing the test object, and confirming
   that the count returns to zero. Correctness-only GSQL queries perform the
   controlled setup and cleanup; the detectors themselves remain the installed
   openCypher queries.

The global checks are correctness checks, not timed benchmark runs. A valid
TPC-H graph must produce `violation_count = 0` for both checks:

- LINEITEM: no two different LINEITEM vertices connected to the same ORDERS
  vertex may have the same `l_linenumber`.
- PARTSUPP: no two different PARTSUPP vertices may connect to the same PART
  and the same SUPPLIER.

The openCypher queries use `getvid(x1) <> getvid(x2)`. If violations exist,
each conflicting unordered pair is matched in both directions; therefore the
reported non-zero count is twice the number of unordered pairs. This does not
affect the zero/non-zero correctness decision.

The retained positive-control result is under
`results/positive_control/20261110_134807/`. Both detectors followed the
expected sequence `0 -> 2 -> 0`, and an additional global verification after
cleanup again returned zero for both entities.

Results are saved under `results/global_correctness_sf<scale>/`. The runner exits
with failure if either count is non-zero or cannot be read from the REST
response.

## Formal performance timing

Run both fixed-position benchmarks with the unified TigerGraph metric:

```powershell
python entity_integrity\scripts\run_entity_benchmark.py --all --scale 0.01
```

Formal performance results are written to timestamped directories under:

```text
results/performance_query_status/sf<scale>/graph/<entity>/<timestamp>/
```

Each query is run 20 times. The five fastest and five slowest
`query_status.elapsedTime` values are discarded, and the remaining ten are
averaged. No TigerGraph DB Hits value is reported because TigerGraph does not
expose a metric equivalent to Neo4j PROFILE DB Hits.

The whole-graph `violation_count` checks remain correctness-only results and
are not included in the performance timing table.
