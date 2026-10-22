# Query installation guide

The benchmark runners call installed TigerGraph query names through RESTPP. They do not
install query definitions. Install the required `CREATE OR REPLACE OPENCYPHER QUERY`
statements in graph `TPCH_G` before running a benchmark.

## Ordinary query files

Use the final comparison variants for Q2, Q8, Q19, and Q20. Use the standard file for the
remaining single-stage queries:

- Q1, Q3--Q7, Q9, Q10, Q12--Q18: `qN/qN_tigergraph.txt`
- Q2, Q8, Q19, Q20: `qN/qN_tigergraph_neo4j_compatible.txt`

Q10 and Q17 already contain the final reference-aligned execution structures used in the
formal series.

## Multi-stage and final-output queries

- Q11: install `q11_threshold_tigergraph.txt` and `q11_values_tigergraph.txt`.
- Q21: install `q21_tigergraph_neo4j_compatible.txt` for the formal comparison series.
- Q22: install `q22_customers_tigergraph.txt` and `q22_order_customers_tigergraph.txt`.

Q11 is run by `run_q11_two_stage.py`. Q21 and Q22 are run by
`run_q21_q22_final.py`. Python transfers intermediate values and constructs the retained
complete CSV outputs where documented.

## Installation method

Each file can be executed in TigerGraph's GSQL environment or pasted into GraphStudio's GSQL
editor while `TPCH_G` is selected. When using a Docker container, copy the selected file into
the container and execute it with the TigerGraph 4.2.4 GSQL client. Container names and host
ports are deliberately not fixed in this review copy because they depend on the local setup.

After installation, run the dry-run commands in `docs/reviewer_guide.md` to verify local file
selection, followed by one real query before starting a complete 20-run series.
