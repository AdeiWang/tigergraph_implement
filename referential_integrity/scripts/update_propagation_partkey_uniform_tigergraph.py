from update_propagation_graph_tigergraph import ChainConfig, run_benchmark


if __name__ == "__main__":
    run_benchmark(ChainConfig(
        code="pc",
        description="PART -> PARTSUPP -> LINEITEM",
        entity_name="PART",
        entity_count=2000,
        key_name="partkey",
        expected_min_key=1,
        expected_max_key=2000,
    ))
