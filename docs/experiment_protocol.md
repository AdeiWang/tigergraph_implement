# Experiment protocol

## Timing rule

Each condition is run 20 times. I sort the database times, remove the fastest five and slowest five, and report the mean of the middle ten. Database time comes from TigerGraph `query_status.elapsedTime`.

## Q1--Q22

Parameter schedules in `results/q*/` are reused across scale factors where possible. For Q11, `fraction` is `0.0001 / scale_factor`. The Neo4j-compatible Q22 run uses the same recorded seven country codes in every repetition.

Q11 time is the sum of its threshold and value queries. Q21 has one timed database query followed by Python processing. Q22 time is the sum of two database queries; Python completes its anti-join and grouping. The extra client interval stored by the Q22 runner is diagnostic, not a complete end-to-end execution time.

## Entity Integrity

Fixed-position checks measure performance. Separate global queries count duplicate PartSupp and Lineitem conceptual keys. The global checks are correctness evidence and are not part of the performance table.

## Referential Integrity

Cc, Oc, Pc, and Sc are tested at requested activation rates of 0.1%, 1%, 10%, 20%, 40%, 60%, 80%, and 100%. Activation, restoration, cleanup, and verification are outside the timed section. The measured operation changes the selected root vertices' business-key property; it does not rewrite downstream vertex properties.

TigerGraph selects a sorted window from a seeded offset. This differs from the global random subset used in the Neo4j Cc and Sc tests, and I report the difference with the results.

## RF1/RF2

An RF result is the sum of the installed openCypher calls in that workload. The runner checks new vertices and typed edges after RF1, then checks their removal after RF2. Setup and correctness checks are not included in database time.

The compact RF values in `examples/project_final_master_summary.csv` belong to the retained
fixed-batch experiment: every scale uses 15 Orders per round and the same total query-call
schedule. They measure the same maintenance batch against differently sized base graphs and
must not be interpreted as a scale-dependent refresh-batch experiment.
