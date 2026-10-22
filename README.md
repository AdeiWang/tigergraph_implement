# TPC-H E/R Graph Workloads for TigerGraph

This repository contains my TigerGraph implementation of the graph-semantics workloads described by Philipp Skavantzos and Sebastian Link. I used TigerGraph 4.2.4 and openCypher for measured query and update operations. GSQL is used to create and load the graph, and for setup or cleanup steps that are not timed.

It covers TPC-H Q1--Q22 at scale factors 0.01, 0.1, and 1; Entity Integrity checks; the Cc, Oc, Pc, and Sc Referential Integrity workloads; and an adapted RF1/RF2 graph-maintenance workload. TPC-H data, full raw results, dissertation files, container data, and credentials are not included.

## Environment

- TigerGraph Community Edition 4.2.4
- Python 3.11.9
- Docker Desktop on Windows 10

```powershell
python -m pip install -r requirements.txt
```

## Directory layout

```text
setup/                              Schema and data-loading scripts
queries_and_refresh_operations/     Q1--Q22 runners and RF1/RF2
entity_integrity/                   Entity Integrity checks
referential_integrity/              Referential Integrity workloads
results/q*/                         Parameter schedules for the 20 runs
examples/                            Small result summary
docs/                                Experiment and migration notes
```

## Preparing the graph

Generate TPC-H data for SF 0.01, 0.1, or 1, then convert it to the vertex and edge CSV files expected by the loading jobs. The sample scripts use `/home/tigergraph/tpch_data/graph/` inside the container; change this path if the data are stored elsewhere. The schema is `setup/schema_graph.gsql`.

## Running Q1--Q22

Install the required queries in `TPCH_G` first. Each test uses 20 runs. I sort the 20 database times, remove the fastest five and slowest five, and report the mean of the middle ten.

Check the runner configuration without connecting to TigerGraph:

```powershell
python queries_and_refresh_operations/scripts/run_benchmark.py --queries 1,3,4,5,6,7,9,10,11,12,13,14,15,16,17,18 --scale 0.01 --dry-run
python queries_and_refresh_operations/scripts/run_benchmark.py --queries 2,8,19,20 --variant neo4j-compatible --scale 0.01 --dry-run
```

For comparison with the Neo4j reference workload, I use the compatible files for Q2, Q8, Q19, and Q20. Q11 runs in two stages because its threshold cannot be passed through one TigerGraph openCypher statement in the same way. The main runner selects this version automatically.

Q21 and Q22 use a separate runner because Python is needed to produce their complete final CSV files:

```powershell
python queries_and_refresh_operations/scripts/run_q21_q22_final.py --query both --q21-variant neo4j-compatible --q22-variant neo4j-compatible --scale 0.01
```

The main runner does not accept Q21 or Q22, which prevents an intermediate database result from being used as the final result. Q11 and Q22 each use two database calls; their database time is the sum of those calls.

## Other experiments

See `entity_integrity/README.md`, `referential_integrity/README.md`, and `queries_and_refresh_operations/rf1_rf2/README.md`. Check the host, graph, scale factor, and entity counts before running them.

## Timing and interpretation

TigerGraph database time comes from `query_status.elapsedTime`. I do not report a TigerGraph equivalent of Neo4j DB Hits because the systems do not provide the same metric. Cross-system results compare implementation and scaling trends; they are not a controlled product ranking.

The global Entity Integrity queries count duplicate conceptual E/R keys. Zero means these checks found no duplicate, not that TigerGraph enforces the keys automatically.

The RF scripts create and delete the vertices and relationships needed for this experiment. They do not include every attribute from the official TPC-H refresh tuples, so I treat them as graph-maintenance workloads rather than complete TPC-H refresh functions.

## Included results

`examples/project_final_master_summary.csv` contains a compact summary. Full timestamped results are not included because they are large. Parameter schedules under `results/q*/` are included so the same inputs can be reused.

## Licence

No open-source licence is included at present.
