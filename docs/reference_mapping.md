# Neo4j reference to TigerGraph mapping

This table identifies where the main components of the Neo4j reference experiment are
represented in this TigerGraph implementation. It documents correspondence, not statement
identity or controlled performance equivalence.

| Reference component | TigerGraph component | Main adaptation |
|---|---|---|
| Neo4j graph-semantics model | `setup/schema_graph.gsql` | Stable artificial Primary IDs are separated from business and conceptual E/R keys. |
| Q1--Q22 Cypher workload | `queries_and_refresh_operations/q*/` | Labels and relationship directions are mapped to the TigerGraph schema; unsupported expressions are rewritten or decomposed. |
| Query execution scripts | `queries_and_refresh_operations/scripts/` | RESTPP asynchronous submission and `query_status.elapsedTime` replace Neo4j PROFILE timing. |
| Q11 single-statement threshold flow | Two Q11 installed queries plus Python scalar transfer | The same two-stage implementation is used at all three scales. |
| Q21 supplier aggregation | Q21 installed query plus Python finalisation | Complete final CSV is retained outside the timed database query. |
| Q22 threshold and anti-join | Two installed queries plus Python finalisation | Database time is the sum of two calls; retrieval and client grouping are reported separately. |
| Neo4j technical node identity | TigerGraph Primary ID | Artificial stable IDs prevent business-key updates from changing vertex identity. |
| Temporary `ACTIVATED` label | Integer `ri_active` root attribute | Activation and cleanup are untimed setup operations. |
| Temporary string-form key | Reversible negative integer business key | Preserves the strongly typed TigerGraph property schema. |
| Cc/Sc global random subset | Sorted seeded window | Selects the requested count reproducibly but may introduce locality. |
| Oc/Pc offset selection | Explicitly sorted seeded window | Makes the selected window deterministic. |
| Neo4j update-propagation chain | Cc/Oc/Pc/Sc root update | Under graph semantics the timed step updates activated root business-key properties; downstream foreign-key copies do not exist. |
| Neo4j constraint/key checks | Fixed-position and global verification queries | TigerGraph checks conceptual E/R keys explicitly rather than claiming native enforcement. |
| Neo4j RF1/RF2 | `queries_and_refresh_operations/rf1_rf2/` | Vertex and relationship mutations are decomposed into installed openCypher calls and use reduced test attributes. |
| Neo4j DB Hits | No TigerGraph substitute | No synthetic DB Hits metric is reported. |

The reference implementation is available at
<https://github.com/graphdbexperiments/er_graph_experiments>.
