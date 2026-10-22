CREATE OR REPLACE OPENCYPHER QUERY rf2_delete_lineitems(
    INT order_key
) FOR GRAPH TPCH_RF_G {
  MATCH (l:RF_LINEITEM)-[:RF_LINEITEM_ORDERS]->(o:RF_ORDERS)
  WHERE o.o_orderkey = $order_key
  DETACH DELETE l
}
