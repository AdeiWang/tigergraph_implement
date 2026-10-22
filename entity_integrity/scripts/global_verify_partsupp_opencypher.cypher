CREATE OR REPLACE OPENCYPHER QUERY global_verify_partsupp()
FOR GRAPH TPCH_G {
  MATCH
    (ps1:G_PARTSUPP)
      -[:G_PARTSUPP_SUPPLIER]->(s:G_SUPPLIER)
      <-[:G_PARTSUPP_SUPPLIER]-(ps2:G_PARTSUPP),
    (ps1:G_PARTSUPP)
      -[:G_PARTSUPP_PART]->(p:G_PART)
      <-[:G_PARTSUPP_PART]-(ps2:G_PARTSUPP)
  WHERE getvid(ps1) <> getvid(ps2)
  RETURN COUNT(*) AS violation_count
}
