from update_propagation_graph_tigergraph import ChainConfig, run_benchmark


if __name__ == "__main__":
    run_benchmark(ChainConfig(
        code="cc",
        description="CUSTOMER -> ORDERS",
        entity_name="CUSTOMER",
        entity_count=1500,
        key_name="custkey",
        expected_min_key=1,
        expected_max_key=1500,
    ))
