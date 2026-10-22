# Q17

`q17_tigergraph.txt` first computes average quantity for every Part, then applies
the brand and container filters in the second match. This follows the execution
order of the Neo4j reference query.

TigerGraph uses `SUM(l_extendedprice / 7.0)` here instead of
`SUM(l_extendedprice) / 7.0`. The two expressions are algebraically equivalent.
