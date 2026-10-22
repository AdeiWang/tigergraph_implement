# Q11

Q11 uses two installed queries at SF 0.01, 0.1, and 1. `q11_threshold_tigergraph.txt` calculates the threshold for the selected nation, and `q11_values_tigergraph.txt` aggregates values by Part and applies it.

Python passes the scalar threshold between the queries. Database time is the sum of both `query_status.elapsedTime` values. This keeps the two logical stages of the Neo4j reference query, although Neo4j passes the value through `WITH` in one statement.

The runner makes extra synchronous calls to retrieve full output for validation. Therefore, `round_wall_ms` is diagnostic and is not the reported Q11 database time.

```powershell
python queries_and_refresh_operations\scripts\run_q11_two_stage.py --scale 0.01
python queries_and_refresh_operations\scripts\run_benchmark.py --query 11 --scale 0.01
```
