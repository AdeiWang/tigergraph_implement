# Entity Integrity

`scripts/run_entity_benchmark.py` runs the fixed-position Lineitem and PartSupp
performance checks using `query_status.elapsedTime`. Each condition uses 20
repetitions and the common 5+5 trimming rule.

`scripts/run_global_correctness_verification.py` runs the two whole-graph
duplicate-key checks. A valid loaded graph should report `violation_count=0`.
Those counts are correctness evidence and are not performance measurements.

Example:

```powershell
python entity_integrity/scripts/run_entity_benchmark.py --all --scale 0.01 --host http://localhost:14240
python entity_integrity/scripts/run_global_correctness_verification.py --scale 0.01 --host http://localhost:14240
```
