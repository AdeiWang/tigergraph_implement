from update_propagation_graph_tigergraph import ChainConfig, run_benchmark


if __name__ == "__main__":
    run_benchmark(ChainConfig(
        code="oc",
        description="ORDERS -> LINEITEM",
        entity_name="ORDERS",
        entity_count=15000,
        key_name="orderkey",
        expected_min_key=1,
        expected_max_key=60000,
    ))
