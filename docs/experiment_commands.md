# Experiment commands

The commands below describe the order used in the project. Container names and host ports may
need adjustment in another installation. Do not load a second scale into a graph that still
contains data from a previous scale.

## 1. Prepare the graph

1. Generate TPC-H source data for the selected scale factor.
2. Convert the source tables into vertex and edge staging CSVs:

```powershell
python setup/convert_tpch_sql_to_csv_parameterized.py --help
```

3. Execute `setup/schema_graph.gsql` in GSQL.
4. Execute the appropriate loading-job definition and run file from `setup/`.
5. Execute `setup/indexes_graph.gsql` where the experiment requires the documented lookup indexes.
6. Check vertex and edge counts before installing queries.

The loading structure is scale independent. The `sf01` filename denotes the SF 0.1 run in
which that file was introduced; it can load SF 0.01 staging files when given the corresponding
paths. Separate clean containers/databases were used for the formal scales.

## 2. Install analytical queries

Follow `docs/query_installation.md`. The runner assumes that all selected query names are
already installed in `TPCH_G`.

## 3. Validate the runner configuration

```powershell
python queries_and_refresh_operations/scripts/run_benchmark.py --queries 1,3,4,5,6,7,9,10,11,12,13,14,15,16,17,18 --scale 0.01 --dry-run
python queries_and_refresh_operations/scripts/run_benchmark.py --queries 2,8,19,20 --variant neo4j-compatible --scale 0.01 --dry-run
```

Repeat with `--scale 0.1` or `--scale 1` as required.

## 4. Run Q1--Q20

```powershell
python queries_and_refresh_operations/scripts/run_benchmark.py --queries 1,3,4,5,6,7,9,10,11,12,13,14,15,16,17,18 --scale 0.01
python queries_and_refresh_operations/scripts/run_benchmark.py --queries 2,8,19,20 --variant neo4j-compatible --scale 0.01
```

Q11 is automatically routed to its two-stage runner. Q2, Q8, Q19, and Q20 use the retained
reference-compatible variants for the formal comparison series.

## 5. Run Q21 and Q22

```powershell
python queries_and_refresh_operations/scripts/run_q21_q22_final.py --query both --q21-variant neo4j-compatible --q22-variant neo4j-compatible --scale 0.01
```

The specialised runner saves complete final CSV outputs. Q22's reported database metric is
the sum of two status-reported database times; Python finalisation is outside that metric.

## 6. Entity Integrity

```powershell
python entity_integrity/scripts/run_entity_benchmark.py --all --scale 0.01 --host http://localhost:14240
python entity_integrity/scripts/run_global_correctness_verification.py --scale 0.01 --host http://localhost:14240
```

The first command measures fixed-position checks. The second performs untimed global
duplicate-key verification.

## 7. Referential Integrity

Run the four entry points after installing the corresponding activation, update, restoration,
and verification queries listed in `referential_integrity/README.md`:

```powershell
python referential_integrity/scripts/update_propagation_custkey_tigergraph.py --help
python referential_integrity/scripts/update_propagation_orderkey_tigergraph.py --help
python referential_integrity/scripts/update_propagation_partkey_uniform_tigergraph.py --help
python referential_integrity/scripts/update_propagation_suppkey_tigergraph.py --help
```

Only the root business-key update is timed. Activation, restoration, cleanup, and correctness
checks are outside the reported database interval.

## 8. RF1/RF2

RF experiments use the isolated `TPCH_RF_G` graph and the files under
`queries_and_refresh_operations/rf1_rf2/`. Review the host profiles before running:

```powershell
python queries_and_refresh_operations/rf1_rf2/scripts/run_rf1_rf2_tigergraph.py --scale 0.01
python queries_and_refresh_operations/rf1_rf2/scripts/run_rf1_rf2_tigergraph.py --scale 0.01 --formal
```

The included summary records the retained historical fixed-batch experiment. It is an adapted
graph-maintenance workload rather than a complete implementation of official TPC-H refresh tuples.
