# Q21

- `q21_tigergraph_neo4j_compatible.txt` follows the Neo4j reference workload and does not add `o_orderstatus = 'F'`.
- `q21_tigergraph_tpch_corrected.txt` follows the official TPC-H condition and includes finished orders only.

Both return the counts needed to calculate `numwait`. `../scripts/run_q21_q22_final.py` performs that calculation, sorts the result, and writes a complete CSV for each run. The corrected variant also applies the official `LIMIT 100`. Python processing is outside database time.
