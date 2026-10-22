CREATE OR REPLACE OPENCYPHER QUERY global_verify_lineitem()
FOR GRAPH TPCH_G {
  MATCH
    (l1:G_LINEITEM)
      -[:G_LINEITEM_ORDERS]->(o:G_ORDERS)
      <-[:G_LINEITEM_ORDERS]-(l2:G_LINEITEM)
  WHERE getvid(l1) <> getvid(l2)
    AND l1.l_linenumber = l2.l_linenumber
  RETURN COUNT(*) AS violation_count
}
