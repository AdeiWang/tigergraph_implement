CREATE OR REPLACE OPENCYPHER QUERY rf1_create_order(
    STRING order_id,
    INT order_key
) FOR GRAPH TPCH_RF_G {
  CREATE (o:RF_ORDERS {
      id: $order_id,
      o_orderkey: $order_key,
      o_comment: "new"
  })
}
