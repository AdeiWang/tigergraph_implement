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
