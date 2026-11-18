# Adapted RF1/RF2 workload

`scripts/run_rf1_rf2_tigergraph.py` runs the isolated refresh experiment. RF1
creates test Orders and Lineitem vertices plus their typed relationships. RF2
removes the same objects so that each cycle restores its starting state.

TigerGraph 4.2.4 openCypher requires separate installed queries for the vertex
and relationship mutations. The reported database time is the sum of their
`query_status.elapsedTime` values. The implementation is an adapted
graph-maintenance workload, not a complete reproduction of every attribute in
the official TPC-H refresh tuples.

The script contains the isolated-container host profiles used in the experiment.
Review those values before running it in another environment.

The final formal workload uses 15, 150, and 1,500 Orders per round at SF 0.01,
0.1, and 1, respectively. Each scale has 20 completed rounds, and all RF1 and
RF2 graph-state checks passed. The retained trimmed means are:

| Scale | RF1 (ms) | RF2 (ms) |
|---|---:|---:|
| 0.01 | 5,028.4 | 1,079.0 |
| 0.1 | 44,508.9 | 17,093.5 |
| 1 | 444,659.6 | 841,308.6 |

These values describe the adapted, decomposed openCypher graph-maintenance
workload. They are not a controlled product-speed comparison with Neo4j.
