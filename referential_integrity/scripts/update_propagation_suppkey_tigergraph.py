from update_propagation_graph_tigergraph import ChainConfig, run_benchmark


if __name__ == "__main__":
    run_benchmark(ChainConfig(
        code="sc",
        description="SUPPLIER -> PARTSUPP -> LINEITEM",
        entity_name="SUPPLIER",
        entity_count=100,
        key_name="suppkey",
        expected_min_key=1,
        expected_max_key=100,
    ))
