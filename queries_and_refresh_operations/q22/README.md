# Q22

Q22 is split into two read-only openCypher queries. `q22_customers_tigergraph.txt` returns customers in the selected phone prefixes, while `q22_order_customers_tigergraph.txt` identifies which of them have an order.

`../scripts/run_q21_q22_final.py` calculates the positive-balance average, removes customers who have orders, groups the remaining rows by country code, and saves the final CSV. Database time is the sum of both `query_status.elapsedTime` values; Python processing is not included.

The Neo4j-compatible run uses `25,23,11,14,13,30,28`. The reference query takes the first seven distinct prefixes without `ORDER BY`, and its saved results do not record the selected prefixes. I use the first distinct prefixes in source customer/import order and record this as an assumption.

The runner also stores an `end_to_end_*` field. It covers later retrieval calls and Python processing, not a complete one-pass execution, so it is diagnostic only.
