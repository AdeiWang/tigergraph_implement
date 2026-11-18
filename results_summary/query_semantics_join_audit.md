# Relational and Mixed Query Join Audit

Date: 10 November 2026

## Purpose

This audit verifies the dissertation statement that the disconnected property-equality join
observed in the Q2 pilot also occurs in 19 of the 22 relational query definitions and 18 of
the 22 mixed query definitions in the Neo4j reference artefacts.

## Source and decision rule

The inspected source was `er_graph_experiments-main.zip`, supplied with the reference
implementation. For each `q1_cypher.txt` to `q22_cypher.txt`, the relational and mixed
sections were inspected separately.

A query was marked **yes** when at least one of its reference-semantic formulations contains:

1. vertex patterns that are not connected to one another by an edge pattern in the relevant
   `MATCH`; and
2. a property-equality predicate that supplies the reference between those patterns, for
   example `ps.ps_partkey = p.p_partkey`.

An equality predicate between vertices already connected by an edge was not counted as a
disconnected join. The audit records query structure, not whether TigerGraph can execute every
other construct in a query.

## Query-level result

| Query | Relational | Mixed | Principal observation |
|---|---:|---:|---|
| Q1 | No | No | Local Lineitem query. |
| Q2 | Yes | Yes | PartSupp--Part and PartSupp--Supplier property joins. |
| Q3 | Yes | Yes | Lineitem--Orders property join remains in mixed. |
| Q4 | Yes | Yes | Orders--Lineitem property join. |
| Q5 | Yes | Yes | Lineitem--Orders and PartSupp--Supplier property joins remain in mixed. |
| Q6 | No | No | Local Lineitem query. |
| Q7 | Yes | Yes | Supplier--Lineitem and Orders--Lineitem property joins remain in mixed. |
| Q8 | Yes | Yes | The mixed definition retains disconnected/property-mediated components. |
| Q9 | Yes | Yes | PartSupp--Supplier, PartSupp--Part, and Lineitem--Orders joins remain in mixed. |
| Q10 | Yes | Yes | Lineitem--Orders property join remains in mixed. |
| Q11 | Yes | Yes | PartSupp--Supplier property join remains in mixed. |
| Q12 | Yes | Yes | Lineitem--Orders property join. |
| Q13 | Yes | No | Mixed uses an Orders--Customer edge; its additional equality is not a disconnected join. |
| Q14 | Yes | Yes | PartSupp--Part property join remains in mixed. |
| Q15 | Yes | Yes | PartSupp--Supplier property join remains in mixed. |
| Q16 | Yes | Yes | PartSupp--Part property join. |
| Q17 | Yes | Yes | PartSupp--Part property join remains in mixed. |
| Q18 | Yes | Yes | Lineitem--Orders property join remains in mixed. |
| Q19 | Yes | Yes | Part--PartSupp property join remains in mixed. |
| Q20 | Yes | Yes | PartSupp--Supplier and PartSupp--Part property joins remain in mixed. |
| Q21 | Yes | Yes | PartSupp--Supplier and Lineitem--Orders property joins remain in mixed. |
| Q22 | No | No | No disconnected property-equality join of this form. |

## Totals

- Relational: Q2--Q5 and Q7--Q21 = **19/22**.
- Mixed: Q2--Q5, Q7--Q12, and Q14--Q21 = **18/22**.

The exceptions are therefore Q1, Q6, and Q22 for relational semantics, and Q1, Q6, Q13,
and Q22 for mixed semantics. Absence of this particular join does not by itself establish that
an entire query definition is executable through TigerGraph openCypher.
