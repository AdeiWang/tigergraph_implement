CREATE OR REPLACE OPENCYPHER QUERY rf1_create_lineitem(
    STRING lineitem_id,
    INT line_number
) FOR GRAPH TPCH_RF_G {
  CREATE (l:RF_LINEITEM {
      id: $lineitem_id,
      l_linenumber: $line_number,
      l_comment: "new"
  })
}
