# Reviewer guide

This repository is the compact review copy of the TigerGraph implementation used in the
dissertation. It excludes generated TPC-H data, Docker volumes, diagnostic logs, and
dissertation source files. The retained formal evidence is included under `evidence/`.

## Suggested inspection route

1. Read the project scope and measurement qualifications in the root `README.md`.
2. Inspect `setup/schema_graph.gsql` for the eight vertex types, stable technical IDs, business-key properties, and typed E/R links.
3. Inspect `docs/query_migration_table.md` for the Q1--Q22 migration classification.
4. Inspect `queries_and_refresh_operations/scripts/query_specs.py` for the formal query/variant selection and parameter schedules.
5. Inspect Q11, Q21, and Q22 together with their specialised runners; these queries cross database/client execution boundaries.
6. Inspect the Entity and Referential Integrity READMEs for the separation of performance timing and correctness checks.
7. Inspect `examples/project_final_master_summary.csv` for the aggregate dissertation results.
8. Inspect `evidence/` for the selected raw timings, summaries, manifests, and correctness records.
9. Inspect `results_summary/` for module-level tables and result provenance.
10. Inspect `figures/` for the selected schema and experimental-result figures.

For correspondence with the reference Neo4j repository, see
`docs/reference_mapping.md`. For an end-to-end command order, see
`docs/experiment_commands.md`.

## Minimal non-database checks

The following commands validate file discovery and the formal query selection without
connecting to TigerGraph:

```powershell
python queries_and_refresh_operations/scripts/run_benchmark.py --queries 1,3,4,5,6,7,9,10,11,12,13,14,15,16,17,18 --scale 0.01 --dry-run
python queries_and_refresh_operations/scripts/run_benchmark.py --queries 2,8,19,20 --variant neo4j-compatible --scale 0.01 --dry-run
```

Q21 and Q22 are intentionally absent from the unified runner because their complete outputs
require specialised client-side finalisation. Their entry point is
`queries_and_refresh_operations/scripts/run_q21_q22_final.py`.

## Evidence boundaries

- Formal execution records exist for Q1--Q22 at SF 0.01, 0.1, and 1.
- Independent SF 0.01 source-data validation is retained for one representative parameter case from each of Q1, Q3, Q6, Q7, and Q18; additional checks cover Q11, Q14, Q16, Q21, and Q22.
- Entity Integrity global checks and reversible positive controls test duplicate detection; they do not demonstrate native key enforcement.
- Referential Integrity correctness checks establish cleanup of activation markers and temporary negative keys, not a retained per-vertex before/after audit.
- RF1/RF2 are adapted graph-maintenance workloads and do not reproduce every official TPC-H refresh-tuple attribute.
- Cross-system figures support descriptive implementation and scaling comparisons, not an uncontrolled product-speed ranking.
