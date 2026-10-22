CREATE OR REPLACE OPENCYPHER QUERY ri_oc_update()
FOR GRAPH TPCH_G {
  MATCH (o:G_ORDERS)
  WHERE o.ri_active = 1
  SET o.o_orderkey = 0 - o.o_orderkey
  RETURN COUNT(o) AS updated_count
}
