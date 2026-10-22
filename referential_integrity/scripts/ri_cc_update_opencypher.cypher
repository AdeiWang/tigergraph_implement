CREATE OR REPLACE OPENCYPHER QUERY ri_cc_update()
FOR GRAPH TPCH_G {
  MATCH (c:G_CUSTOMER)
  WHERE c.ri_active = 1
  SET c.c_custkey = 0 - c.c_custkey
  RETURN COUNT(c) AS updated_count
}
