# Referential Integrity update workloads

The current entry points are:

- `update_propagation_custkey_tigergraph.py` (Cc)
- `update_propagation_orderkey_tigergraph.py` (Oc)
- `update_propagation_partkey_uniform_tigergraph.py` (Pc)
- `update_propagation_suppkey_tigergraph.py` (Sc)

They share `update_propagation_graph_tigergraph.py` and execute eight requested
activation percentages with 20 repetitions each. GSQL performs untimed
activation/restoration/cleanup; installed openCypher performs the timed root-key
update. Review the scale and host arguments before execution.

Under graph semantics, the dependency-chain names describe the reference
structure. The timed operation changes the activated root business-key
properties and does not propagate copied foreign-key values downstream.
