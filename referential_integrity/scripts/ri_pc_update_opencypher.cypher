CREATE OR REPLACE OPENCYPHER QUERY ri_pc_update()
FOR GRAPH TPCH_G {

  MATCH (p:G_PART)
  WHERE p.ri_active = 1

  SET p.p_partkey = 0 - p.p_partkey

  RETURN COUNT(p) AS updated_count
}