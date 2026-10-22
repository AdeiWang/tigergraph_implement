CREATE OR REPLACE OPENCYPHER QUERY rf2_delete_order(
    INT order_key
) FOR GRAPH TPCH_RF_G {
  MATCH (o:RF_ORDERS)
  WHERE o.o_orderkey = $order_key
  DETACH DELETE o
}
