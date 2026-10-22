CREATE OR REPLACE OPENCYPHER QUERY ri_sc_update()
FOR GRAPH TPCH_G {
  MATCH (s:G_SUPPLIER)
  WHERE s.ri_active = 1
  SET s.s_suppkey = 0 - s.s_suppkey
  RETURN COUNT(s) AS updated_count
}
