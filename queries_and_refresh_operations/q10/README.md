# Q10

`q10_tigergraph.txt` keeps the complete
`LINEITEM -> ORDERS -> CUSTOMER -> NATION` pattern in one match. TigerGraph
requires the non-aggregate `WITH` expressions to appear before `SUM(...)`.
